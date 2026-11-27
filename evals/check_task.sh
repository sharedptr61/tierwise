#!/usr/bin/env bash
# Prove a task's hidden tests: they must fail on the untouched repository and pass with the reference solution.
set -u
T=$1; W=$(mktemp -d); cp -r "$T/repo/." "$W/"; cp -r "$T/hidden" "$W/hidden_eval"
(cd "$W" && python3 -m unittest discover -s hidden_eval 2>&1 | tail -1 | sed 's/^/  original:  /')
cp -r "$T/reference/." "$W/"
[ -f "$T/reference/DELETE" ] && (cd "$W" && xargs rm -f < "$T/reference/DELETE")
(cd "$W" && python3 -m unittest discover -s hidden_eval 2>&1 | tail -1 | sed 's/^/  reference: /'
          python3 -m unittest discover -s tests -t . 2>&1 | tail -1 | sed 's/^/  visible:   /')
rm -rf "$W"
