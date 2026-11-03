# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# An app's per-app GPU choice for gpu-diag.sh (ANAL-336), kept in Android's three updatable-driver lists as OpenBook
# Graphics and Developer options › Graphics Driver Preferences keep it (AppDriver.kt): the prerelease opt-in list,
# the opt-in list (NVIDIA) and the opt-out list (Radeon). An app's "state" is its membership of the three, in that
# order, e.g. "0 1 0" for NVIDIA.
#
# Sourced. The caller provides:
#   sh_ CMD   runs CMD in the device's shell; stdout without CRs; fails when adb fails
#   PENDING   the journal's path
# Every read and write is checked: the device must report the settings command's own exit status 0. Nothing is
# assumed from a failure. The journal is written before the first change and removed only once a read-back shows
# the app's original state, or shows the owner changed it.

OPT_IN=updatable_driver_production_opt_in_apps
OPT_OUT=updatable_driver_production_opt_out_apps
PRE_IN=updatable_driver_prerelease_opt_in_apps
CHOICE_LISTS=("$PRE_IN" "$OPT_IN" "$OPT_OUT")

# getlist KEY: the list's value ("" for unset). Fails unless the device ran `settings get` and it succeeded.
getlist() {
  local out
  out=$(sh_ "settings get global $1; echo \"@rc=\$?\"") || return 1
  case $out in *@rc=0) ;; *) return 1 ;; esac
  out=${out%@rc=0}; out=${out%$'\n'}
  [ "$out" = null ] && out=
  printf '%s\n' "$out"
}
# putlist KEY VALUE: write (or delete, for "") and check the device's settings command succeeded. Refuses a value
# with characters a package list can't have, so nothing needs quoting beyond single quotes.
putlist() {
  local out
  [[ $2 =~ ^[A-Za-z0-9_.,*-]*$ ]] || { echo "choice: refusing to write $1='$2'" >&2; return 1; }
  if [ -n "$2" ]; then out=$(sh_ "settings put global $1 '$2'; echo \"@rc=\$?\"") || return 1
  else out=$(sh_ "settings delete global $1; echo \"@rc=\$?\"") || return 1; fi
  case $out in *@rc=0) return 0 ;; *) return 1 ;; esac
}
inlist() { tr ',' '\n' <<<"$2" | grep -qxF "$1"; }
# edit LIST_VALUE PKG ADD(0|1) [POS]: the list without PKG and empty entries, plus PKG when ADD=1, at entry POS
# (0-based; default or past the end: last). Every other entry stays, in order.
edit() {
  { tr ',' '\n' <<<"$1" | grep -vxF "$2" | grep . || true; } |
    awk -v p="$2" -v add="$3" -v pos="${4:--1}" 'add == 1 && NR - 1 == pos {print p; done = 1} {print}
      END {if (add == 1 && !done) print p}' | paste -sd, -
}
# position PKG LIST_VALUE: PKG's 0-based entry among the list's non-empty entries, or -1
position() { tr ',' '\n' <<<"$2" | grep . | grep -nxF "$1" | head -n 1 | awk -F: '{print $1 - 1; f = 1} END {if (!f) print -1}'; }

# state PKG: "P I O", PKG's membership of the prerelease opt-in, opt-in and opt-out lists. Fails on any failed read.
# positions PKG: PKG's entry in each of them (-1: absent), so a restore puts it back where it was.
state() {
  local k v s=
  for k in "${CHOICE_LISTS[@]}"; do
    v=$(getlist "$k") || return 1
    if inlist "$1" "$v"; then s+="1 "; else s+="0 "; fi
  done
  echo "${s% }"
}
positions() {
  local k v s=
  for k in "${CHOICE_LISTS[@]}"; do v=$(getlist "$k") || return 1; s+="$(position "$1" "$v") "; done
  echo "${s% }"
}
state_for() {  # automatic|nvidia|radeon -> the state choosing it leaves (no prerelease entry)
  case $1 in nvidia) echo "0 1 0" ;; radeon) echo "0 0 1" ;; automatic) echo "0 0 0" ;; *) return 1 ;; esac
}
choice_name() {  # "P I O" -> what Android does with it (opt-out wins over opt-in; prerelease over opt-in)
  local p i o; read -r p i o <<<"$1"
  if [ "$o" = 1 ]; then echo radeon; elif [ "$p" = 1 ]; then echo prerelease; elif [ "$i" = 1 ]; then echo nvidia
  else echo automatic; fi
}

# path FROM TO: the states apply_state passes through on its way from FROM to TO, one list at a time in
# CHOICE_LISTS order, FROM and TO included. An interrupted change leaves the app on this path and nowhere else.
path() {
  local f=($1) t=($2) i
  echo "$1"
  for i in 0 1 2; do
    if [ "${f[$i]}" != "${t[$i]}" ]; then f[$i]=${t[$i]}; echo "${f[*]}"; fi
  done
}
# journal FIELD=VALUE...: rewrite the journal with these fields replaced or added, atomically.
journal() {
  local kv k
  cp "$PENDING" "$PENDING.tmp" || return 1
  for kv in "$@"; do
    k=${kv%%=*}
    { grep -v "^$k=" "$PENDING.tmp" || true; echo "$kv"; } > "$PENDING.tmp2" && mv "$PENDING.tmp2" "$PENDING.tmp" || return 1
  done
  mv "$PENDING.tmp" "$PENDING"
}

# apply_state PKG "P I O" ["POSITIONS"]: change only PKG's entries, list by list, then read back. Fails unless the
# read-back shows exactly that state.
apply_state() {
  local pkg=$1 want=($2) pos=(${3:--1 -1 -1}) have k v h n=0
  h=$(state "$pkg") || return 1
  have=($h)
  for k in "${CHOICE_LISTS[@]}"; do
    if [ "${have[$n]}" != "${want[$n]}" ]; then
      v=$(getlist "$k") || return 1
      putlist "$k" "$(edit "$v" "$pkg" "${want[$n]}" "${pos[$n]}")" || return 1
    fi
    n=$((n + 1))
  done
  [ "$(state "$pkg")" = "$2" ]
}

# choose PKG automatic|nvidia|radeon: journal PKG's state (phase=setting), set the choice, verify it, then mark the
# journal phase=set. On failure the journal stays at phase=setting, so restore_pending undoes whatever part was
# applied.
choose() {
  local pkg=$1 orig set pos
  set=$(state_for "$2") || { echo "choice: unknown choice $2" >&2; return 1; }
  orig=$(state "$pkg") && pos=$(positions "$pkg") || { echo "choice: could not read $pkg's GPU choice" >&2; return 1; }
  if [ "$orig" = "$set" ]; then echo "choice: $pkg is already $2 ($orig); nothing to change"; return 0; fi
  printf 'pkg=%s\noriginal=%s\npositions=%s\nset=%s\nphase=setting\nowner=%s\nsince=%s\n' "$pkg" "$orig" "$pos" \
    "$set" "${OPENBOOK_G14_LOCK_OWNER:-}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$PENDING.tmp" &&
    mv "$PENDING.tmp" "$PENDING" || return 1
  apply_state "$pkg" "$set" || { echo "choice: setting $pkg to $2 failed; the journal stays" >&2; return 1; }
  journal phase=set || { echo "choice: could not mark the journal; it stays at phase=setting" >&2; return 1; }
  echo "choice: $pkg $(choice_name "$orig") ($orig) -> $2 ($set); restored after the run"
}

# restore_pending: put back the journalled app's original state. 0: restored, already as before, or the owner
# changed it (kept); the journal is removed. 1: anything could not be read, written or verified; the journal stays.
# Whose state it is depends on the journal's phase:
#   set        the run's choice was applied and verified: only exactly that state is the run's; anything else is
#              the owner's choice and is kept
#   setting    the set was interrupted: any state on the way from the original to the run's choice is the run's
#   restoring  a restore was interrupted: any state on the way from where it started to the original is the run's
# A journal without a phase (written by an older gpu-diag) counts as "setting".
restore_pending() {
  [ -s "$PENDING" ] || return 0
  local pkg orig set pos cur phase from ours=0
  pkg=$(sed -n 's/^pkg=//p' "$PENDING"); orig=$(sed -n 's/^original=//p' "$PENDING"); set=$(sed -n 's/^set=//p' "$PENDING")
  pos=$(sed -n 's/^positions=//p' "$PENDING"); [[ $pos =~ ^-?[0-9]+\ -?[0-9]+\ -?[0-9]+$ ]] || pos="-1 -1 -1"
  phase=$(sed -n 's/^phase=//p' "$PENDING"); from=$(sed -n 's/^from=//p' "$PENDING")
  [ -n "$phase" ] || phase=setting
  if ! [[ $pkg =~ ^[A-Za-z][A-Za-z0-9_.]*$ && $orig =~ ^[01]\ [01]\ [01]$ && $set =~ ^[01]\ [01]\ [01]$ &&
          $phase =~ ^(setting|set|restoring)$ ]] || { [ "$phase" = restoring ] && ! [[ $from =~ ^[01]\ [01]\ [01]$ ]]; }; then
    echo "restore: unreadable journal $PENDING; kept" >&2; return 1
  fi
  cur=$(state "$pkg") || { echo "restore: could not read $pkg's GPU choice; journal kept" >&2; return 1; }
  if [ "$cur" = "$orig" ]; then
    echo "restore: $pkg is as before ($(choice_name "$orig"), $orig)"; rm -f "$PENDING"; return 0
  fi
  case $phase in
    set) [ "$cur" = "$set" ] && ours=1 ;;
    setting) path "$orig" "$set" | grep -qxF "$cur" && ours=1 ;;
    restoring) path "$from" "$orig" | grep -qxF "$cur" && ours=1 ;;
  esac
  if [ $ours = 0 ]; then
    echo "restore: kept $pkg's GPU choice: the owner changed it to $(choice_name "$cur") ($cur) during the run" \
      "(the run had set $(choice_name "$set"), $set; journal phase $phase)"
    rm -f "$PENDING"; return 0
  fi
  [ "$phase" = restoring ] || journal phase=restoring "from=$cur" ||
    { echo "restore: could not mark the journal; nothing changed, journal kept" >&2; return 1; }
  apply_state "$pkg" "$orig" "$pos" || { echo "restore: putting back $pkg's GPU choice failed; journal kept" >&2; return 1; }
  echo "restore: $pkg's GPU choice is back to $(choice_name "$orig") ($orig), verified"
  rm -f "$PENDING"
}
