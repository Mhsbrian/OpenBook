// In-app CPU benchmark entry (ANAL-180). Links the unmodified CoreMark sources (posix port, built with
// -Dmain=coremark_main) and returns what CoreMark prints to stdout.
#include <jni.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int coremark_main(int argc, char* argv[]);

JNIEXPORT jstring JNICALL Java_dev_anybook_probe_MainActivity_nativeBench(JNIEnv* env, jclass c, jstring jargs) {
  (void)c;
  char args[256], *argv[16] = {"coremark"};
  int argc = 1;
  const char* a = (*env)->GetStringUTFChars(env, jargs, NULL);
  strncpy(args, a, sizeof args - 1);
  args[sizeof args - 1] = 0;
  (*env)->ReleaseStringUTFChars(env, jargs, a);
  char* save = NULL;
  for (char* t = strtok_r(args, " ", &save); t && argc < 15; t = strtok_r(NULL, " ", &save)) argv[argc++] = t;

  int p[2];
  if (pipe(p) != 0) return (*env)->NewStringUTF(env, "pipe failed");
  fflush(stdout);
  int saved = dup(1);
  dup2(p[1], 1);
  close(p[1]);
  coremark_main(argc, argv);
  fflush(stdout);
  dup2(saved, 1);
  close(saved);
  static char out[16384];
  size_t n = 0;
  ssize_t r;
  while (n < sizeof out - 1 && (r = read(p[0], out + n, sizeof out - 1 - n)) > 0) n += (size_t)r;
  out[n] = 0;
  close(p[0]);
  return (*env)->NewStringUTF(env, out);
}
