#!/bin/sh
# Starts Postgres with its log as JSON lines in the shared log folder's
# postgres/ subfolder, one file a weekday, emptied when the week comes round
# again (postgres-Mon.json). The subfolder is made here and given to the
# image's postgres user, so the folder needs nothing from the installer.
# Postgres refuses to start when it cannot write its log, so with a folder it
# cannot write it logs to the container's output (docker logs webapp-postgres)
# instead, and says so there.
dir=/var/log/kanat/postgres
mkdir -p "$dir" 2>/dev/null
chown postgres:postgres "$dir" 2>/dev/null
if su-exec postgres sh -c "touch '$dir/.writable' && rm -f '$dir/.writable'" 2>/dev/null; then
  exec docker-entrypoint.sh postgres \
    -c logging_collector=on \
    -c log_destination=jsonlog \
    -c "log_directory=$dir" \
    -c log_filename=postgres-%a.log \
    -c log_rotation_age=1d \
    -c log_rotation_size=0 \
    -c log_truncate_on_rotation=on \
    -c log_file_mode=0644 \
    "$@"
fi
echo "start.sh: $dir is not writable: logging to the container's output instead" >&2
exec docker-entrypoint.sh postgres "$@"
