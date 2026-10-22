// SPDX-License-Identifier: Apache-2.0
//
// ANAL-234: run an app's ARM64 Icing library outside ART so native bridges can
// be compared on real hardware without changing the system image.
//
// A small JNI shim stands in for ART: it answers the library's JNI_OnLoad,
// records RegisterNatives, and emulates the few Java classes Icing calls back
// into (String, Locale and Icing's BreakIteratorBatcher, a word iterator over
// ASCII text). The probe then creates an engine, sets a schema, indexes the
// documents from the input file, searches, persists, and repeats the searches
// after a restart on the same directory. Results are written as raw protos for
// `icing-probe.py decode`; this program does not judge them.
//
// usage: icing_probe LIBICING INPUT OUTPUT BASE_DIR TIMED_ROUNDS
//
// build.sh links libm, liblog, libz and libc++ and sets RUNPATH $ORIGIN/guest, so
// every library libicing.so binds to comes from the guest set beside the probe.

#include <ctype.h>
#include <dlfcn.h>
#include <link.h>
#include <jni.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

enum { K_CLASS = 1, K_STRING, K_BYTES, K_INTS, K_LOCALE, K_BITER, K_ENGINE };

struct obj {
  int kind;
  int len;
  char* data;        // string bytes (NUL-terminated), array storage, class name
  int pos;           // break iterator position
  int64_t native_ptr;  // IcingSearchEngineImpl.nativePointer
};

enum {
  M_STRING_CTOR = 1, M_STRING_CODE_POINT_COUNT, M_STRING_LENGTH,
  M_LOCALE_CTOR, M_LOCALE_FOR_TAG,
  M_BI_CTOR, M_BI_SET_TEXT, M_BI_NEXT, M_BI_FIRST, M_BI_FOLLOWING, M_BI_PRECEDING,
  F_NATIVE_POINTER, F_LOCALE_US, M_UNKNOWN,
};

struct member { int id; char name[96]; };

static struct obj* new_obj(int kind, int len) {
  struct obj* o = calloc(1, sizeof(*o));
  o->kind = kind;
  o->len = len;
  o->data = calloc(1, (size_t)(len > 0 ? len : 0) * (kind == K_INTS ? 4 : 1) + 1);
  return o;
}

static struct obj* new_string(const char* s, int len) {
  struct obj* o = new_obj(K_STRING, len);
  memcpy(o->data, s, (size_t)len);
  return o;
}

static int unknown_calls;

static jmethodID member(const char* cls, const char* name, int is_field) {
  static const struct { const char* cls; const char* name; int id; } known[] = {
    {"java/lang/String", "<init>", M_STRING_CTOR},
    {"java/lang/String", "codePointCount", M_STRING_CODE_POINT_COUNT},
    {"java/lang/String", "length", M_STRING_LENGTH},
    {"java/util/Locale", "<init>", M_LOCALE_CTOR},
    {"java/util/Locale", "forLanguageTag", M_LOCALE_FOR_TAG},
    {"java/util/Locale", "US", F_LOCALE_US},
    {"com/google/android/icing/BreakIteratorBatcher", "<init>", M_BI_CTOR},
    {"com/google/android/icing/BreakIteratorBatcher", "setText", M_BI_SET_TEXT},
    {"com/google/android/icing/BreakIteratorBatcher", "next", M_BI_NEXT},
    {"com/google/android/icing/BreakIteratorBatcher", "first", M_BI_FIRST},
    {"com/google/android/icing/BreakIteratorBatcher", "following", M_BI_FOLLOWING},
    {"com/google/android/icing/BreakIteratorBatcher", "preceding", M_BI_PRECEDING},
    {"com/google/android/icing/IcingSearchEngineImpl", "nativePointer", F_NATIVE_POINTER},
  };
  struct member* m = calloc(1, sizeof(*m));
  m->id = M_UNKNOWN;
  snprintf(m->name, sizeof(m->name), "%s.%s", cls, name);
  for (size_t i = 0; i < sizeof(known) / sizeof(known[0]); ++i) {
    if (!strcmp(known[i].cls, cls) && !strcmp(known[i].name, name)) m->id = known[i].id;
  }
  if (m->id == M_UNKNOWN) {
    ++unknown_calls;
    fprintf(stderr, "ICING_PROBE_UNKNOWN_%s %s\n", is_field ? "FIELD" : "METHOD", m->name);
  }
  return (jmethodID)m;
}

static int id_of(const void* m) { return ((const struct member*)m)->id; }

static void fail_member(const void* m) {
  fprintf(stderr, "ICING_PROBE_UNSUPPORTED_CALL %s\n", ((const struct member*)m)->name);
  abort();
}

// Java BreakIterator.getWordInstance() boundaries for ASCII text: runs of word
// characters, runs of whitespace, and every other character on its own.
static int is_word(unsigned char c) { return isalnum(c) || c == '_' || c >= 0x80; }

static int segment_end(const struct obj* text, int i) {
  if (i >= text->len) return -1;
  unsigned char c = (unsigned char)text->data[i];
  int j = i + 1;
  if (is_word(c)) {
    while (j < text->len && is_word((unsigned char)text->data[j])) ++j;
  } else if (isspace(c)) {
    while (j < text->len && isspace((unsigned char)text->data[j])) ++j;
  }
  return j;
}

struct biter { struct obj* text; int pos; };

static struct obj* lookup_class(const char* name) {
  static struct obj* classes[32];
  static int n;
  for (int i = 0; i < n; ++i) if (!strcmp(classes[i]->data, name)) return classes[i];
  struct obj* o = new_string(name, (int)strlen(name));
  o->kind = K_CLASS;
  if (n < 32) classes[n++] = o;
  return o;
}

// ---- JNIEnv ----

static JavaVM vm;
static JNIEnv env;
static struct JNINativeInterface env_fns;
static struct JNIInvokeInterface vm_fns;

struct native { char name[64]; void* fn; };
static struct native natives[96];
static int native_count;

static jint GetVersion(JNIEnv* e) { (void)e; return JNI_VERSION_1_6; }
static jclass FindClass(JNIEnv* e, const char* name) { (void)e; return (jclass)lookup_class(name); }
static jthrowable ExceptionOccurred(JNIEnv* e) { (void)e; return NULL; }
static void ExceptionDescribe(JNIEnv* e) { (void)e; }
static void ExceptionClear(JNIEnv* e) { (void)e; }
static jboolean ExceptionCheck(JNIEnv* e) { (void)e; return JNI_FALSE; }
static jint PushLocalFrame(JNIEnv* e, jint c) { (void)e; (void)c; return 0; }
static jobject PopLocalFrame(JNIEnv* e, jobject o) { (void)e; return o; }
static jobject NewRef(JNIEnv* e, jobject o) { (void)e; return o; }
static void DeleteRef(JNIEnv* e, jobject o) { (void)e; (void)o; }
static jboolean IsSameObject(JNIEnv* e, jobject a, jobject b) { (void)e; return a == b; }
static jint EnsureLocalCapacity(JNIEnv* e, jint c) { (void)e; (void)c; return 0; }
static jobjectRefType GetObjectRefType(JNIEnv* e, jobject o) { (void)e; (void)o; return JNILocalRefType; }

static jmethodID GetMethodID(JNIEnv* e, jclass c, const char* name, const char* sig) {
  (void)e; (void)sig;
  return member(((struct obj*)c)->data, name, 0);
}
static jfieldID GetFieldID(JNIEnv* e, jclass c, const char* name, const char* sig) {
  (void)e; (void)sig;
  return (jfieldID)member(((struct obj*)c)->data, name, 1);
}

static jobject new_object(jmethodID m, const jvalue* a) {
  switch (id_of(m)) {
    case M_STRING_CTOR: {  // String(byte[] utf8, String charsetName)
      struct obj* bytes = (struct obj*)a[0].l;
      return (jobject)new_string(bytes->data, bytes->len);
    }
    case M_LOCALE_CTOR: {
      struct obj* tag = (struct obj*)a[0].l;
      struct obj* o = new_string(tag->data, tag->len);
      o->kind = K_LOCALE;
      return (jobject)o;
    }
    case M_BI_CTOR: {
      struct obj* o = new_obj(K_BITER, 0);
      o->data = calloc(1, sizeof(struct biter));
      return (jobject)o;
    }
  }
  fail_member(m);
  return NULL;
}

// Every method here takes at most two int/object arguments; read them in order.
static void read_args(jmethodID m, va_list ap, jvalue* a) {
  switch (id_of(m)) {
    case M_STRING_CTOR: a[0].l = va_arg(ap, jobject); a[1].l = va_arg(ap, jobject); break;
    case M_LOCALE_CTOR: case M_BI_CTOR: case M_BI_SET_TEXT: case M_LOCALE_FOR_TAG:
      a[0].l = va_arg(ap, jobject); break;
    case M_BI_NEXT: case M_BI_FOLLOWING: case M_BI_PRECEDING: a[0].i = va_arg(ap, jint); break;
    case M_STRING_CODE_POINT_COUNT: a[0].i = va_arg(ap, jint); a[1].i = va_arg(ap, jint); break;
    default: break;
  }
}

static jobject NewObjectA(JNIEnv* e, jclass c, jmethodID m, const jvalue* a) {
  (void)e; (void)c;
  return new_object(m, a);
}
static jobject NewObjectV(JNIEnv* e, jclass c, jmethodID m, va_list ap) {
  jvalue a[2] = {{0}};
  read_args(m, ap, a);
  return NewObjectA(e, c, m, a);
}
static jobject NewObject(JNIEnv* e, jclass c, jmethodID m, ...) {
  va_list ap;
  va_start(ap, m);
  jobject o = NewObjectV(e, c, m, ap);
  va_end(ap);
  return o;
}

static struct biter* biter_of(jobject o) {
  struct obj* b = (struct obj*)o;
  if (b->kind != K_BITER) { fprintf(stderr, "ICING_PROBE_BAD_ITERATOR\n"); abort(); }
  return (struct biter*)b->data;
}

static jint call_int(jobject self, jmethodID m, const jvalue* a) {
  switch (id_of(m)) {
    case M_STRING_LENGTH: return ((struct obj*)self)->len;
    case M_STRING_CODE_POINT_COUNT: return a[1].i - a[0].i;  // ASCII input only
    case M_BI_FIRST: { struct biter* b = biter_of(self); b->pos = 0; return 0; }
    case M_BI_FOLLOWING: {
      struct biter* b = biter_of(self);
      int p = 0;
      while (p <= a[0].i) { p = segment_end(b->text, p); if (p < 0) return -1; }
      b->pos = p;
      return p;
    }
    case M_BI_PRECEDING: {
      struct biter* b = biter_of(self);
      if (a[0].i <= 0) return -1;
      int p = 0;
      for (;;) { int q = segment_end(b->text, p); if (q < 0 || q >= a[0].i) break; p = q; }
      b->pos = p;
      return p;
    }
  }
  fail_member(m);
  return 0;
}

static jobject call_object(jobject self, jmethodID m, const jvalue* a) {
  switch (id_of(m)) {
    case M_BI_NEXT: {  // int[] of up to batchSize following boundaries
      struct biter* b = biter_of(self);
      struct obj* out = new_obj(K_INTS, a[0].i);
      int n = 0;
      while (n < a[0].i) {
        int p = segment_end(b->text, b->pos);
        if (p < 0) break;
        b->pos = p;
        ((jint*)out->data)[n++] = p;
      }
      out->len = n;
      return (jobject)out;
    }
    case M_LOCALE_FOR_TAG: {
      struct obj* tag = (struct obj*)a[0].l;
      struct obj* o = new_string(tag->data, tag->len);
      o->kind = K_LOCALE;
      return (jobject)o;
    }
  }
  fail_member(m);
  return NULL;
}

static void call_void(jobject self, jmethodID m, const jvalue* a) {
  if (id_of(m) == M_BI_SET_TEXT) {
    struct biter* b = biter_of(self);
    b->text = (struct obj*)a[0].l;
    b->pos = 0;
    for (int i = 0; i < b->text->len; ++i) {
      if ((unsigned char)b->text->data[i] >= 0x80) {
        fprintf(stderr, "ICING_PROBE_NON_ASCII_TEXT\n");
        abort();
      }
    }
    return;
  }
  fail_member(m);
}

#define CALL_FAMILY(NAME, TYPE, IMPL)                                                   \
  static TYPE NAME##A(JNIEnv* e, jobject o, jmethodID m, const jvalue* a) {            \
    (void)e; return IMPL(o, m, a);                                                      \
  }                                                                                     \
  static TYPE NAME##V(JNIEnv* e, jobject o, jmethodID m, va_list ap) {                  \
    jvalue a[2] = {{0}}; read_args(m, ap, a); return NAME##A(e, o, m, a);               \
  }                                                                                     \
  static TYPE NAME(JNIEnv* e, jobject o, jmethodID m, ...) {                            \
    va_list ap; va_start(ap, m); TYPE r = NAME##V(e, o, m, ap); va_end(ap); return r;   \
  }
CALL_FAMILY(CallIntMethod, jint, call_int)
CALL_FAMILY(CallObjectMethod, jobject, call_object)

static void CallVoidMethodA(JNIEnv* e, jobject o, jmethodID m, const jvalue* a) {
  (void)e; call_void(o, m, a);
}
static void CallVoidMethodV(JNIEnv* e, jobject o, jmethodID m, va_list ap) {
  jvalue a[2] = {{0}}; read_args(m, ap, a); CallVoidMethodA(e, o, m, a);
}
static void CallVoidMethod(JNIEnv* e, jobject o, jmethodID m, ...) {
  va_list ap; va_start(ap, m); CallVoidMethodV(e, o, m, ap); va_end(ap);
}

static jobject CallStaticObjectMethodA(JNIEnv* e, jclass c, jmethodID m, const jvalue* a) {
  (void)e; (void)c; return call_object(NULL, m, a);
}
static jobject CallStaticObjectMethodV(JNIEnv* e, jclass c, jmethodID m, va_list ap) {
  jvalue a[2] = {{0}}; read_args(m, ap, a); return CallStaticObjectMethodA(e, c, m, a);
}
static jobject CallStaticObjectMethod(JNIEnv* e, jclass c, jmethodID m, ...) {
  va_list ap; va_start(ap, m); jobject r = CallStaticObjectMethodV(e, c, m, ap); va_end(ap); return r;
}

static jlong GetLongField(JNIEnv* e, jobject o, jfieldID f) {
  (void)e;
  if (id_of(f) != F_NATIVE_POINTER) fail_member(f);
  return ((struct obj*)o)->native_ptr;
}
static void SetLongField(JNIEnv* e, jobject o, jfieldID f, jlong v) {
  (void)e;
  if (id_of(f) != F_NATIVE_POINTER) fail_member(f);
  ((struct obj*)o)->native_ptr = v;
}
static jobject GetStaticObjectField(JNIEnv* e, jclass c, jfieldID f) {
  (void)e; (void)c;
  if (id_of(f) != F_LOCALE_US) fail_member(f);
  struct obj* o = new_string("en-US", 5);
  o->kind = K_LOCALE;
  return (jobject)o;
}
static jint GetStaticIntField(JNIEnv* e, jclass c, jfieldID f) { (void)e; (void)c; fail_member(f); return 0; }

static jstring NewStringUTF(JNIEnv* e, const char* s) { (void)e; return (jstring)new_string(s, (int)strlen(s)); }
static jsize GetStringLength(JNIEnv* e, jstring s) { (void)e; return ((struct obj*)s)->len; }
static jsize GetStringUTFLength(JNIEnv* e, jstring s) { (void)e; return ((struct obj*)s)->len; }
static const char* GetStringUTFChars(JNIEnv* e, jstring s, jboolean* copy) {
  (void)e; if (copy) *copy = JNI_FALSE; return ((struct obj*)s)->data;
}
static void ReleaseStringUTFChars(JNIEnv* e, jstring s, const char* p) { (void)e; (void)s; (void)p; }

static jsize GetArrayLength(JNIEnv* e, jarray a) { (void)e; return ((struct obj*)a)->len; }
static jbyteArray NewByteArray(JNIEnv* e, jsize n) { (void)e; return (jbyteArray)new_obj(K_BYTES, n); }
static jintArray NewIntArray(JNIEnv* e, jsize n) { (void)e; return (jintArray)new_obj(K_INTS, n); }
static void* elements(jarray a, jboolean* copy) { if (copy) *copy = JNI_FALSE; return ((struct obj*)a)->data; }
static jbyte* GetByteArrayElements(JNIEnv* e, jbyteArray a, jboolean* c) { (void)e; return elements(a, c); }
static void ReleaseByteArrayElements(JNIEnv* e, jbyteArray a, jbyte* p, jint m) { (void)e; (void)a; (void)p; (void)m; }
static jint* GetIntArrayElements(JNIEnv* e, jintArray a, jboolean* c) { (void)e; return elements(a, c); }
static void ReleaseIntArrayElements(JNIEnv* e, jintArray a, jint* p, jint m) { (void)e; (void)a; (void)p; (void)m; }
static void* GetPrimitiveArrayCritical(JNIEnv* e, jarray a, jboolean* c) { (void)e; return elements(a, c); }
static void ReleasePrimitiveArrayCritical(JNIEnv* e, jarray a, void* p, jint m) { (void)e; (void)a; (void)p; (void)m; }
static void GetByteArrayRegion(JNIEnv* e, jbyteArray a, jsize s, jsize n, jbyte* out) {
  (void)e; memcpy(out, ((struct obj*)a)->data + s, (size_t)n);
}
static void SetByteArrayRegion(JNIEnv* e, jbyteArray a, jsize s, jsize n, const jbyte* in) {
  (void)e; memcpy(((struct obj*)a)->data + s, in, (size_t)n);
}

static jint RegisterNatives(JNIEnv* e, jclass c, const JNINativeMethod* m, jint n) {
  (void)e; (void)c;
  for (jint i = 0; i < n && native_count < 96; ++i) {
    snprintf(natives[native_count].name, sizeof(natives[0].name), "%s", m[i].name);
    natives[native_count++].fn = m[i].fnPtr;
  }
  return JNI_OK;
}
static jint GetJavaVM(JNIEnv* e, JavaVM** out) { (void)e; *out = &vm; return JNI_OK; }

static jint vm_GetEnv(JavaVM* v, void** out, jint version) { (void)v; (void)version; *out = &env; return JNI_OK; }
static jint vm_Attach(JavaVM* v, JNIEnv** out, void* args) { (void)v; (void)args; *out = &env; return JNI_OK; }
static jint vm_Detach(JavaVM* v) { (void)v; return JNI_OK; }
static jint vm_Destroy(JavaVM* v) { (void)v; return JNI_OK; }

static void unimplemented(int slot) {
  fprintf(stderr, "ICING_PROBE_UNIMPLEMENTED_JNI slot=%d\n", slot);
  abort();
}
#define STUB(n) static void stub##n(void) { unimplemented(n); }
#define STUB10(n) STUB(n##0) STUB(n##1) STUB(n##2) STUB(n##3) STUB(n##4) \
                  STUB(n##5) STUB(n##6) STUB(n##7) STUB(n##8) STUB(n##9)
#define REF10(n) stub##n##0, stub##n##1, stub##n##2, stub##n##3, stub##n##4, \
                 stub##n##5, stub##n##6, stub##n##7, stub##n##8, stub##n##9
STUB(0) STUB(1) STUB(2) STUB(3) STUB(4) STUB(5) STUB(6) STUB(7) STUB(8) STUB(9)
STUB10(1) STUB10(2) STUB10(3) STUB10(4) STUB10(5) STUB10(6) STUB10(7) STUB10(8) STUB10(9)
STUB10(10) STUB10(11) STUB10(12) STUB10(13) STUB10(14) STUB10(15) STUB10(16) STUB10(17)
STUB10(18) STUB10(19) STUB10(20) STUB10(21) STUB10(22) STUB10(23) STUB10(24) STUB10(25)
static void (*const stubs[])(void) = {
  stub0, stub1, stub2, stub3, stub4, stub5, stub6, stub7, stub8, stub9,
  REF10(1), REF10(2), REF10(3), REF10(4), REF10(5), REF10(6), REF10(7), REF10(8), REF10(9),
  REF10(10), REF10(11), REF10(12), REF10(13), REF10(14), REF10(15), REF10(16), REF10(17),
  REF10(18), REF10(19), REF10(20), REF10(21), REF10(22), REF10(23), REF10(24), REF10(25),
};

static void init_jni(void) {
  void** slots = (void**)&env_fns;
  size_t n = sizeof(env_fns) / sizeof(void*);
  if (n > sizeof(stubs) / sizeof(stubs[0])) { fprintf(stderr, "ICING_PROBE_JNI_TABLE_TOO_LARGE\n"); exit(2); }
  for (size_t i = 0; i < n; ++i) slots[i] = (void*)stubs[i];
#define SET(f) env_fns.f = f
  SET(GetVersion); SET(FindClass); SET(ExceptionOccurred); SET(ExceptionDescribe);
  SET(ExceptionClear); SET(ExceptionCheck); SET(PushLocalFrame); SET(PopLocalFrame);
  env_fns.NewGlobalRef = NewRef; env_fns.NewLocalRef = NewRef;
  env_fns.DeleteGlobalRef = DeleteRef; env_fns.DeleteLocalRef = DeleteRef;
  env_fns.NewWeakGlobalRef = NewRef; env_fns.DeleteWeakGlobalRef = DeleteRef;
  SET(IsSameObject); SET(EnsureLocalCapacity); SET(GetObjectRefType);
  SET(GetMethodID); SET(GetFieldID);
  env_fns.GetStaticMethodID = GetMethodID;
  env_fns.GetStaticFieldID = GetFieldID;
  SET(NewObject); SET(NewObjectV); SET(NewObjectA);
  SET(CallIntMethod); SET(CallIntMethodV); SET(CallIntMethodA);
  SET(CallObjectMethod); SET(CallObjectMethodV); SET(CallObjectMethodA);
  SET(CallVoidMethod); SET(CallVoidMethodV); SET(CallVoidMethodA);
  SET(CallStaticObjectMethod); SET(CallStaticObjectMethodV); SET(CallStaticObjectMethodA);
  SET(GetLongField); SET(SetLongField); SET(GetStaticObjectField); SET(GetStaticIntField);
  SET(NewStringUTF); SET(GetStringLength); SET(GetStringUTFLength);
  SET(GetStringUTFChars); SET(ReleaseStringUTFChars);
  SET(GetArrayLength); SET(NewByteArray); SET(NewIntArray);
  SET(GetByteArrayElements); SET(ReleaseByteArrayElements);
  SET(GetIntArrayElements); SET(ReleaseIntArrayElements);
  SET(GetPrimitiveArrayCritical); SET(ReleasePrimitiveArrayCritical);
  SET(GetByteArrayRegion); SET(SetByteArrayRegion);
  SET(RegisterNatives); SET(GetJavaVM);
#undef SET
  vm_fns.GetEnv = vm_GetEnv;
  vm_fns.AttachCurrentThread = vm_Attach;
  vm_fns.AttachCurrentThreadAsDaemon = vm_Attach;
  vm_fns.DetachCurrentThread = vm_Detach;
  vm_fns.DestroyJavaVM = vm_Destroy;
  env = &env_fns;
  vm = &vm_fns;
}

// ---- probe ----

static void* native(const char* name) {
  for (int i = 0; i < native_count; ++i) if (!strcmp(natives[i].name, name)) return natives[i].fn;
  fprintf(stderr, "ICING_PROBE_MISSING_NATIVE %s\n", name);
  exit(3);
}

struct record { char type; struct obj* bytes; };

static int read_records(const char* path, struct record* out, int max) {
  FILE* f = fopen(path, "rb");
  if (!f) { perror(path); exit(2); }
  int n = 0;
  for (;;) {
    unsigned char h[5];
    if (fread(h, 1, 5, f) != 5) break;
    int len = h[1] | h[2] << 8 | h[3] << 16 | h[4] << 24;
    if (n == max || len < 0 || len > (1 << 24)) { fprintf(stderr, "ICING_PROBE_BAD_INPUT\n"); exit(2); }
    out[n].type = (char)h[0];
    out[n].bytes = new_obj(K_BYTES, len);
    if (fread(out[n].bytes->data, 1, (size_t)len, f) != (size_t)len) { fprintf(stderr, "ICING_PROBE_SHORT_INPUT\n"); exit(2); }
    ++n;
  }
  fclose(f);
  return n;
}

static FILE* out_file;

static void emit(char type, jbyteArray result) {
  struct obj* o = (struct obj*)result;
  int len = o ? o->len : -1;
  unsigned char h[5] = {(unsigned char)type, (unsigned char)len, (unsigned char)(len >> 8),
                        (unsigned char)(len >> 16), (unsigned char)(len >> 24)};
  fwrite(h, 1, 5, out_file);
  if (o) fwrite(o->data, 1, (size_t)o->len, out_file);
  fflush(out_file);
}

static int print_loaded(struct dl_phdr_info* info, size_t size, void* data) {
  (void)size; (void)data;
  if (info->dlpi_name && info->dlpi_name[0]) printf("ICING_PROBE_LOADED %s\n", info->dlpi_name);
  return 0;
}

static double now_ms(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

typedef jlong (*create_fn)(JNIEnv*, jclass, jbyteArray);
typedef jbyteArray (*engine_fn)(JNIEnv*, jclass, jobject);
typedef jbyteArray (*schema_fn)(JNIEnv*, jclass, jobject, jbyteArray, jboolean);
typedef jbyteArray (*bytes_fn)(JNIEnv*, jclass, jobject, jbyteArray);
typedef jbyteArray (*int_fn)(JNIEnv*, jclass, jobject, jint);
typedef jbyteArray (*search_fn)(JNIEnv*, jclass, jobject, jbyteArray, jbyteArray, jbyteArray, jlong);
typedef void (*destroy_fn)(JNIEnv*, jclass, jobject);

static struct obj* create_engine(jclass cls, const char* base_dir) {
  // IcingSearchEngineOptions { base_dir = 1 }
  size_t n = strlen(base_dir);
  if (n > 120) { fprintf(stderr, "ICING_PROBE_BASE_DIR_TOO_LONG\n"); exit(2); }
  struct obj* options = new_obj(K_BYTES, (int)n + 2);
  options->data[0] = 0x0a;
  options->data[1] = (char)n;
  memcpy(options->data + 2, base_dir, n);
  struct obj* engine = new_obj(K_ENGINE, 0);
  engine->native_ptr = ((create_fn)native("nativeCreate"))(&env, cls, (jbyteArray)options);
  if (!engine->native_ptr) { fprintf(stderr, "ICING_PROBE_CREATE_FAILED\n"); exit(4); }
  return engine;
}

int main(int argc, char** argv) {
  if (argc != 6) {
    fprintf(stderr, "usage: %s LIBICING INPUT OUTPUT BASE_DIR TIMED_ROUNDS\n", argv[0]);
    return 2;
  }
  int rounds = atoi(argv[5]);
  static struct record records[8192];
  int count = read_records(argv[2], records, 8192);
  out_file = fopen(argv[3], "wb");
  if (!out_file) { perror(argv[3]); return 2; }
  if (mkdir(argv[4], 0700) != 0) { perror(argv[4]); return 2; }
  init_jni();

  double t0 = now_ms();
  void* lib = dlopen(argv[1], RTLD_NOW);
  if (!lib) { fprintf(stderr, "ICING_PROBE_DLOPEN_FAILED %s\n", dlerror()); return 5; }
  jint (*on_load)(JavaVM*, void*) = (jint (*)(JavaVM*, void*))dlsym(lib, "JNI_OnLoad");
  if (!on_load) { fprintf(stderr, "ICING_PROBE_NO_JNI_ONLOAD\n"); return 5; }
  jint version = on_load(&vm, NULL);
  double t_load = now_ms();
  printf("ICING_PROBE_ONLOAD version=0x%x natives=%d unknown_members=%d load_ms=%.1f\n",
         version, native_count, unknown_calls, t_load - t0);
  dl_iterate_phdr(print_loaded, NULL);
  fflush(stdout);
  if (version != JNI_VERSION_1_6) return 5;

  jclass cls = (jclass)lookup_class("com/google/android/icing/IcingSearchEngineImpl");
  struct obj* engine = create_engine(cls, argv[4]);
  emit('I', ((engine_fn)native("nativeInitialize"))(&env, cls, (jobject)engine));
  double t_init = now_ms();

  struct obj *scoring = NULL, *result_spec = NULL;
  int docs = 0, queries = 0;
  double t_index0 = 0, t_index = 0;
  for (int i = 0; i < count; ++i) {
    struct record* r = &records[i];
    if (r->type == 'S') {
      emit('S', ((schema_fn)native("nativeSetSchema"))(&env, cls, (jobject)engine, (jbyteArray)r->bytes, JNI_FALSE));
      t_index0 = now_ms();
    } else if (r->type == 'D') {
      emit('P', ((bytes_fn)native("nativePut"))(&env, cls, (jobject)engine, (jbyteArray)r->bytes));
      ++docs;
      t_index = now_ms();
    } else if (r->type == 'C') {
      scoring = r->bytes;
    } else if (r->type == 'R') {
      result_spec = r->bytes;
    }
  }
  if (!scoring || !result_spec) { fprintf(stderr, "ICING_PROBE_MISSING_SPECS\n"); return 2; }

  search_fn search = (search_fn)native("nativeSearch");
  double t_search0 = now_ms();
  for (int i = 0; i < count; ++i) {
    if (records[i].type != 'Q') continue;
    emit('Q', search(&env, cls, (jobject)engine, (jbyteArray)records[i].bytes,
                     (jbyteArray)scoring, (jbyteArray)result_spec, (jlong)0));
    ++queries;
  }
  double t_search = now_ms();
  for (int round = 0; round < rounds; ++round) {
    for (int i = 0; i < count; ++i) {
      if (records[i].type != 'Q') continue;
      if (!search(&env, cls, (jobject)engine, (jbyteArray)records[i].bytes,
                  (jbyteArray)scoring, (jbyteArray)result_spec, (jlong)0)) {
        fprintf(stderr, "ICING_PROBE_TIMED_SEARCH_NULL\n");
        return 6;
      }
    }
  }
  double t_rounds = now_ms();
  emit('F', ((int_fn)native("nativePersistToDisk"))(&env, cls, (jobject)engine, 2 /* FULL */));
  ((destroy_fn)native("nativeDestroy"))(&env, cls, (jobject)engine);
  double t_close = now_ms();

  // Restart on the same directory, as the app does after its process is killed.
  engine = create_engine(cls, argv[4]);
  emit('J', ((engine_fn)native("nativeInitialize"))(&env, cls, (jobject)engine));
  for (int i = 0; i < count; ++i) {
    if (records[i].type != 'Q') continue;
    emit('K', search(&env, cls, (jobject)engine, (jbyteArray)records[i].bytes,
                     (jbyteArray)scoring, (jbyteArray)result_spec, (jlong)0));
  }
  ((destroy_fn)native("nativeDestroy"))(&env, cls, (jobject)engine);
  double t_end = now_ms();

  printf("ICING_PROBE_DONE docs=%d queries=%d timed_rounds=%d load_ms=%.1f init_ms=%.1f "
         "index_ms=%.1f first_search_ms=%.1f timed_search_ms=%.1f persist_close_ms=%.1f "
         "restart_ms=%.1f total_ms=%.1f\n",
         docs, queries, rounds, t_load - t0, t_init - t_load, t_index - t_index0,
         t_search - t_search0, t_rounds - t_search, t_close - t_rounds, t_end - t_close,
         t_end - t0);
  fclose(out_file);
  return 0;
}
