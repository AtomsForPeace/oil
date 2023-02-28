#!/usr/bin/env bash
#
# Handle build dependencies that are in tarballs.
#
# Usage:
#   deps/from-tar.sh <function name>
#
# Examples:
#   deps/from-tar.sh download-re2c
#   deps/from-tar.sh build-re2c
#
# The executable will be in ../oil_DEPS/re2c/re2c.

set -o nounset
set -o pipefail
set -o errexit

REPO_ROOT=$(cd "$(dirname $0)/.."; pwd)
readonly REPO_ROOT

readonly DEPS_DIR=$REPO_ROOT/../oil_DEPS

source build/common.sh  # $PREPARE_DIR, $PY27

clean-temp() {
  ### Works for layer-bloaty now.  TODO: re2c, cmark, Python 3, spec-bin
  rm -r -f -v _cache/
}

#
# re2c dependency
#

readonly RE2C_VERSION=3.0

download-re2c() {
  # local cache of remote files
  mkdir -p _cache
  wget --no-clobber --directory _cache \
    https://github.com/skvadrik/re2c/releases/download/$RE2C_VERSION/re2c-$RE2C_VERSION.tar.xz
}

# TODO: Use make install to minimize
build-re2c() {
  cd $REPO_ROOT/_cache
  tar -x --xz < re2c-$RE2C_VERSION.tar.xz

  mkdir -p $DEPS_DIR/re2c
  cd $DEPS_DIR/re2c
  $REPO_ROOT/_cache/re2c-$RE2C_VERSION/configure
  make
}

#
# cmark dependency
#

readonly CMARK_VERSION=0.29.0
readonly CMARK_URL="https://github.com/commonmark/cmark/archive/$CMARK_VERSION.tar.gz"

download-cmark() {
  mkdir -p $REPO_ROOT/_cache
  wget --no-clobber --directory $REPO_ROOT/_cache $CMARK_URL
}

extract-cmark() {
  pushd $REPO_ROOT/_cache
  tar -x -z < $(basename $CMARK_URL)
  popd
}

# TODO: Use make install
build-cmark() {
  mkdir -p $DEPS_DIR/cmark
  pushd $DEPS_DIR/cmark

  # Configure
  cmake $REPO_ROOT/_cache/cmark-0.29.0/

  # Compile
  make

  # This tests with Python 3, but we're using cmark via Python 2.
  # It crashes on some systems due to the renaming of cgi.escape -> html.escape
  # (issue 792)
  # The 'demo-ours' test is good enough for us.
  #make test

  popd

  # Binaries are in build/src
}

symlink-cmark() {
  #sudo make install
  ln -s -f -v $DEPS_DIR/cmark/src/libcmark.so $DEPS_DIR/
  ls -l $DEPS_DIR/libcmark.so
}

#
# CPython 3.10 dependency for Pea
#

readonly PY3_VERSION=3.10.4
readonly PY3_URL="https://www.python.org/ftp/python/3.10.4/Python-$PY3_VERSION.tar.xz"

download-py3() {
  mkdir -p $REPO_ROOT/_cache
  wget --no-clobber --directory $REPO_ROOT/_cache $PY3_URL
}

extract-py3() {
  pushd $REPO_ROOT/_cache
  tar -x --xz < $(basename $PY3_URL)
  popd
}

symlink-py3() {
  ln -s -f -v $DEPS_DIR/py3/python $DEPS_DIR/python3
  ls -l $DEPS_DIR/python3
}

test-py3() {
  $DEPS_DIR/python3 -c 'import sys; print(sys.version)'
}

configure-python() {
  ### for both 2.7 OVM slice and 3.10 mycpp

  local dir=${1:-$PREPARE_DIR}
  local conf=${2:-$PWD/$PY27/configure}

  rm -r -f $dir
  mkdir -p $dir

  pushd $dir 
  time $conf
  popd
}

# Clang makes this faster.  We have to build all modules so that we can
# dynamically discover them with py-deps.
#
# Takes about 27 seconds on a fast i7 machine.
# Ubuntu under VirtualBox on MacBook Air with 4 cores (3 jobs): 1m 25s with
# -O2, 30 s with -O0.  The Make part of the build is parallelized, but the
# setup.py part is not!

readonly NPROC=$(nproc)
readonly JOBS=$(( NPROC == 1 ? NPROC : NPROC-1 ))

build-python() {
  local dir=${1:-$PREPARE_DIR}

  pushd $dir
  make clean
  time make -j $JOBS
  popd
}

#
# Layer Definitions
#

layer-cmark() {
  extract-cmark
  build-cmark
  symlink-cmark
}

layer-re2c() {
  download-re2c
  build-re2c
}

layer-cpython() {
  configure-python
  build-python
}

# For Pea and type checking
layer-py3() {
  # Dockerfile.pea copies it
  # download-py3

  extract-py3

  local dir=$DEPS_DIR/py3
  configure-python $dir $REPO_ROOT/_cache/Python-$PY3_VERSION/configure
  build-python $dir

  symlink-py3
}

# Bloaty doesn't seem to be available in Debian/Ubuntu repos

download-bloaty() {
  wget --no-clobber --directory $REPO_ROOT/_cache \
    https://github.com/google/bloaty/releases/download/v1.1/bloaty-1.1.tar.bz2
}

extract-bloaty() {
  pushd $REPO_ROOT/_cache
  tar -x -j < bloaty-1.1.tar.bz2
  popd
}

readonly BLOATY_DIR="$REPO_ROOT/_cache/bloaty-1.1"

build-bloaty() {
  mkdir -p $BLOATY_DIR/build
  pushd $BLOATY_DIR/build

  # It's much slower without -G Ninja!
  cmake -G Ninja $BLOATY_DIR

  # Limit parallelism.  This build is ridiculously expensive?
  ninja -j 4

  popd
}

install-bloaty() {
  mkdir -p ../oil_DEPS/bin
  strip -o ../oil_DEPS/bin/bloaty $BLOATY_DIR/build/bloaty
  ../oil_DEPS/bin/bloaty --help
}

layer-bloaty() {
  # tarball should be copied into Docker

  extract-bloaty
  build-bloaty
  install-bloaty
}

bloaty-sizes() {
  # 52 M
  du --si -s _cache/bloaty*

  # 694 MB, OK we have to fix this
  du --si -s $DEPS_DIR/bin/bloaty
}


download-wild() {
  ### Done outside the container

  mkdir -p $REPO_ROOT/_cache
  wget --directory $REPO_ROOT/_cache --no-clobber \
    https://www.oilshell.org/blob/wild/wild-source.tar.gz
}

extract-wild() {
  ### Done in the container build

  mkdir -p $DEPS_DIR/wild/src
  pushd $DEPS_DIR/wild/src
  tar --extract -z < $REPO_ROOT/_cache/wild-source.tar.gz
  popd
}

"$@"
