#!/usr/bin/python
"""
comp_builtins.py - Completion builtins
"""

from core import args
from core import builtin
from core import completion
from core import state
from core import util

from _devbuild.gen import osh_help  # generated file

log = util.log


def _DefineFlags(spec):
  spec.ShortFlag('-F', args.Str, help='Complete with this function')
  spec.ShortFlag('-P', args.Str,
      help='Prefix is added at the beginning of each possible completion after '
           'all other options have been applied.')
  spec.ShortFlag('-S', args.Str,
      help='Suffix is appended to each possible completion after '
           'all other options have been applied.')


def _DefineOptions(spec):
  """Common -o options for complete and compgen."""

  # bashdefault, default, filenames, nospace are used in git
  spec.Option(None, 'bashdefault',
      help='If nothing matches, perform default bash completions')
  spec.Option(None, 'default',
      help="If nothing matches, use readline's default filename completion")
  spec.Option(None, 'filenames',
      help="The completion function generates filenames and should be "
           "post-processed")
  spec.Option(None, 'nospace',
      help="Don't append a space to words completed at the end of the line")


def _DefineActions(spec):
  """Common -A actions for complete and compgen."""

  # NOTE: git-completion.bash uses -f and -v. 
  # My ~/.bashrc on Ubuntu uses -d, -u, -j, -v, -a, -c, -b
  spec.InitActions()
  spec.Action('a', 'alias')
  spec.Action('b', 'binding')
  spec.Action('c', 'command')
  spec.Action('d', 'directory')
  spec.Action('f', 'file')
  spec.Action('j', 'job')
  spec.Action('u', 'user')
  spec.Action('v', 'variable')
  spec.Action(None, 'function')
  spec.Action(None, 'helptopic')  # help
  spec.Action(None, 'setopt')  # set -o
  spec.Action(None, 'shopt')  # shopt -s
  spec.Action(None, 'signal')  # kill -s
  spec.Action(None, 'stopped')


class _SortedWordsAction(object):
  def __init__(self, d):
    self.d = d

  def Matches(self, words, index, prefix):
    for name in sorted(self.d):
      if name.startswith(prefix):
        #yield name + ' '  # full word
        yield name


class _DirectoriesAction(object):
  """complete -A directory"""

  def Matches(self, words, index, prefix):
    raise NotImplementedError('-A directory')


class _UsersAction(object):
  """complete -A user"""

  def Matches(self, words, index, prefix):
    raise NotImplementedError('-A user')


def _BuildCompletionChain(argv, arg, ex):
  """Given flags to complete/compgen, built a ChainedCompleter."""
  actions = []
  # NOTE: bash doesn't actually check the name until completion time, but
  # obviously it's better to check here.
  if arg.F:
    func_name = arg.F
    func = ex.funcs.get(func_name)
    if func is None:
      raise args.UsageError('Function %r not found' % func_name)
    actions.append(completion.ShellFuncAction(ex, func))

  # NOTE: We need completion for -A action itself!!!  bash seems to have it.
  for name in arg.actions:
    if name == 'alias':
      a = _SortedWordsAction(ex.aliases)

    elif name == 'binding':
      # TODO: Where do we get this from?
      a = _SortedWordsAction(['vi-delete'])

    elif name == 'command':
      # TODO: This needs keywords too
      actions.append(_SortedWordsAction(builtin.BUILTIN_NAMES))

      a = completion.ExternalCommandAction(ex.mem)

    elif name == 'directory':
      # TODO: This is FileSystemAction with a filter
      a = _DirectoriesAction()

    elif name == 'file':
      a = completion.FileSystemAction()

    elif name == 'function':
      a = _SortedWordsAction(ex.funcs)

    elif name == 'job':
      a = _SortedWordsAction(['jobs-not-implemented'])

    elif name == 'user':
      a = _UsersAction()

    elif name == 'variable':
      a = completion.VariablesAction(ex.mem)

    elif name == 'helptopic':
      a = _SortedWordsAction(osh_help.TOPIC_LOOKUP)

    elif name == 'setopt':
      a = _SortedWordsAction(state.SET_OPTION_NAMES)

    elif name == 'shopt':
      a = _SortedWordsAction(state.SHOPT_OPTION_NAMES)

    elif name == 'signal':
      a = _SortedWordsAction(['TODO:signals'])

    elif name == 'stopped':
      a = _SortedWordsAction(['jobs-not-implemented'])

    else:
      raise NotImplementedError(name)

    actions.append(a)

  if not actions:
    raise args.UsageError('No actions defined in completion: %s' % argv)

  chain = completion.ChainedCompleter(
      actions,
      prefix=arg.P or '',
      suffix=arg.S or '')

  return chain


# git-completion.sh uses complete -o and complete -F
COMPLETE_SPEC = args.FlagsAndOptions()

_DefineFlags(COMPLETE_SPEC)
_DefineOptions(COMPLETE_SPEC)
_DefineActions(COMPLETE_SPEC)

COMPLETE_SPEC.ShortFlag('-E',
    help='Define the compspec for an empty line')
COMPLETE_SPEC.ShortFlag('-D',
    help='Define the compspec that applies when nothing else matches')


def Complete(argv, ex, comp_lookup):
  """complete builtin - register a completion function.

  NOTE: It's a member of Executor because it creates a ShellFuncAction, which
  needs an Executor.
  """
  arg_r = args.Reader(argv)
  arg = COMPLETE_SPEC.Parse(arg_r)
  # TODO: process arg.opt_changes
  #log('arg %s', arg)

  commands = arg_r.Rest()

  if arg.D:
    commands.append('__fallback')  # if the command doesn't match anything
  if arg.E:
    commands.append('__first')  # empty line

  if not commands:
    comp_lookup.PrintSpecs()
    return 0

  chain = _BuildCompletionChain(argv, arg, ex)
  for command in commands:
    comp_lookup.RegisterName(command, chain)

  patterns = []
  for pat in patterns:
    comp_lookup.RegisterGlob(pat, chain)

  return 0


COMPGEN_SPEC = args.FlagsAndOptions()  # for -o and -A

_DefineFlags(COMPGEN_SPEC)
_DefineOptions(COMPGEN_SPEC)
_DefineActions(COMPGEN_SPEC)


def CompGen(argv, ex):
  """Print completions on stdout."""

  arg_r = args.Reader(argv)
  arg = COMPGEN_SPEC.Parse(arg_r)

  if arg_r.AtEnd():
    to_complete = ''
  else:
    to_complete = arg_r.Peek()
    arg_r.Next()
    if not arg_r.AtEnd():
      raise args.UsageError('Extra arguments')

  matched = False

  chain = _BuildCompletionChain(argv, arg, ex)

  # TODO:
  # - need to dedupe these, as in RootCompleter
  # - what to pass for comp_words and index?
  matched = False 
  for m in chain.Matches(None, None, to_complete):
    matched = True
    print(m)

  return 0 if matched else 1


COMPOPT_SPEC = args.FlagsAndOptions()  # for -o
_DefineOptions(COMPOPT_SPEC)


def CompOpt(argv):
  arg_r = args.Reader(argv)
  arg = COMPOPT_SPEC.Parse(arg_r)

  # NOTE: This is supposed to fail if a completion isn't being generated?
  # The executor should have a mode?

  log('arg %s', arg)
  return 0
