# back up existing shells
cp -a ~/.zshrc ~/.zshrc.bak.$(date +%s) 2>/dev/null || true
cp -a ~/.bashrc ~/.bashrc.bak.$(date +%s) 2>/dev/null || true
cp -a ~/.bash_profile ~/.bash_profile.bak.$(date +%s) 2>/dev/null || true

# the block we'll append
BLOCK='
# --- GStreamer + Homebrew env (persistent) ---
HB_PREFIX="$(brew --prefix)"
GST_PREFIX="$(brew --prefix gstreamer)"

export PATH="$HB_PREFIX/bin:$PATH"
export DYLD_FALLBACK_LIBRARY_PATH="$HB_PREFIX/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
export GI_TYPELIB_PATH="$HB_PREFIX/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"

export GST_PLUGIN_SCANNER="$GST_PREFIX/libexec/gstreamer-1.0/gst-plugin-scanner"
export GST_PLUGIN_SYSTEM_PATH="$GST_PREFIX/lib/gstreamer-1.0"
export GST_PLUGIN_SYSTEM_PATH_1_0="$GST_PLUGIN_SYSTEM_PATH"
# --- end GStreamer + Homebrew env ---
'

# append to zshrc (idempotent)
grep -q "GStreamer + Homebrew env (persistent)" ~/.zshrc 2>/dev/null || printf "%s\n" "$BLOCK" >> ~/.zshrc

# append to bashrc (idempotent)
grep -q "GStreamer + Homebrew env (persistent)" ~/.bashrc 2>/dev/null || printf "%s\n" "$BLOCK" >> ~/.bashrc

# ensure bash_profile sources bashrc
if [ ! -f ~/.bash_profile ] || ! grep -q 'source ~/.bashrc' ~/.bash_profile 2>/dev/null; then
  printf '\n# Load user bashrc if present\n[ -f ~/.bashrc ] && source ~/.bashrc\n' >> ~/.bash_profile
fi

# load into current shell (run both; one will apply)
[ -n "$ZSH_VERSION" ] && source ~/.zshrc
[ -n "$BASH_VERSION" ] && source ~/.bashrc

# show what we set
echo "GST_PLUGIN_SCANNER=$GST_PLUGIN_SCANNER"
echo "GST_PLUGIN_SYSTEM_PATH=$GST_PLUGIN_SYSTEM_PATH"
echo "GI_TYPELIB_PATH=$GI_TYPELIB_PATH"
echo "DYLD_FALLBACK_LIBRARY_PATH=$DYLD_FALLBACK_LIBRARY_PATH"
