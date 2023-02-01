"""
alloc.py - FAILED attempt at memory management.

TODO: Just use a straightforward graph and rely on the garbage collector.
There's NO ARENA.

The idea is to save the LST for functions, but discard it for commands that
have already executed.  Each statement/function can be parsed into a separate
Arena, and the entire Arena can be discarded at once.

Also, we don't want to save comment lines.
"""

from _devbuild.gen.syntax_asdl import source_t, Token, SourceLine
from asdl import runtime
from core.pyerror import log

from typing import List, Dict, Any

_ = log


class ctx_Location(object):

  def __init__(self, arena, src):
    # type: (Arena, source_t) -> None
    arena.PushSource(src)
    self.arena = arena

  def __enter__(self):
    # type: () -> None
    pass

  def __exit__(self, type, value, traceback):
    # type: (Any, Any, Any) -> None
    self.arena.PopSource()


class Arena(object):
  """A collection line spans and associated debug info.

  Use Cases:
  1. Error reporting
  2. osh-to-oil Translation
  """
  def __init__(self):
    # type: () -> None

    # All lines that haven't been discarded.  For LST formatting.
    self.lines_list = []  # type: List[SourceLine]

    # Lines explicitly saved from lines_list.
    self.saved_lines = []  # type: List[SourceLine]

    # Three parallel arrays indexed by line_id.
    self.line_vals = []  # type: List[str]
    self.line_nums = []  # type: List[int]
    self.line_srcs = []  # type: List[source_t]
    self.line_num_strs = {}  # type: Dict[int, str]  # an INTERN table

    # indexed by span_id
    self.tokens = []  # type: List[Token]

    # reuse these instances in many line_span instances
    self.source_instances = []  # type: List[source_t]

  def PushSource(self, src):
    # type: (source_t) -> None
    self.source_instances.append(src)

  def PopSource(self):
    # type: () -> None
    self.source_instances.pop()

  def AddLine(self, line, line_num):
    # type: (str, int) -> int
    """Save a physical line and return a line_id for later retrieval.

    The line number is 1-based.
    """
    line_id = len(self.line_vals)
    self.line_vals.append(line)
    self.line_nums.append(line_num)
    self.line_srcs.append(self.source_instances[-1])

    # New scheme
    src_line = SourceLine(line_num, line_id, line, self.source_instances[-1])
    self.lines_list.append(src_line)

    return line_id

  def DiscardLines(self):
    # type: () -> None
    """Remove references ot lines we've accumulated.

    - This makes the linear search in SnipCodeString() shorter.
    - It removes the ARENA's references to all lines.  The TOKENS still
      reference some lines.
    """
    #log("discarding %d lines", len(self.lines_list))
    del self.lines_list[:]

  def SaveLinesAndDiscard(self, left, right):
    # type: (Token, Token) -> None
    """
    Save the lines between two tokens, e.g. for { and }

    Why?
    - In between { }, we want to preserve lines not pointed to by a token, e.g.
      comment lines.
    - But we don't want to save all lines in an interactive shell:
      echo 1
      echo 2
      ...
      echo 500000
      echo 500001

    The lines should be freed after execution takes place.
    """
    #log('*** Saving lines between %r and %r', left, right)

    num_saved = 0
    saving = False
    for li in self.lines_list:
      if li.line_id == left.line_id:
        saving = True

      # These lines are PERMANENT, and never deleted.  What if you overwrite a
      # function name?  You might want to save those in a the function record
      # ITSELF.
      #
      # This is for INLINE hay blocks that can be evaluated at any point.  In
      # contrast, parse_hay(other_file) uses ParseWholeFile, and we could save
      # all lines.

      # TODO: consider creating a new Arena for each CommandParser?  Or rename itj
      # to 'BackingLines' or something.

      # TODO: We should mutate li.line_id here so it's the index into
      # saved_lines?
      if saving:
        self.saved_lines.append(li)
        log('   %r', li.val)
        num_saved += 1

      if li.line_id == right.line_id:
        saving = False
        break

    log('*** SAVED %d lines', num_saved)

    self.DiscardLines()

    #log('SAVED = %s', [line.val for line in self.saved_lines])

  def SnipCodeString(self, left, right):
    # type: (Token, Token) -> str
    """Return the code string between left and right tokens, INCLUSIVE.  

    Used for ALIAS expansion, which happens in the PARSER.  So we use
    self.lines_list, not self.saved_lines.

    The argument to aliases can span multiple lines, like htis:

    $ myalias '1
        2
        3'
    """
    pieces = []  # type: List[str]
    saving = False
    for li in self.lines_list:
      if li.line_id == left.line_id:
        saving = True

        # Save everything after the left token
        piece = li.val[left.col:]
        pieces.append(piece)
        log('   %r', piece)
        continue

      if li.line_id == right.line_id:
        piece = li.val[ : right.col + right.length]
        pieces.append(piece)
        log('   %r', piece)

        saving = False
        break

      # TODO: We should mutate li.line_id here so it's the index into saved_lines?
      if saving:
        pieces.append(li.val)
        log('   %r', li.val)

    assert len(pieces), "Couldn't find tokens in lines list"
    return ''.join(pieces)

  def GetLine(self, line_id):
    # type: (int) -> str
    """Return the text of a line.

    TODO: This should be hidden behind an interface like Python's line cache?
    It should store offsets (and maybe checkums).  It will have two
    implementions: in-memory for interactive, and on-disk for batch and
    'sourced' files.
    """
    assert line_id >= 0, line_id
    return self.line_vals[line_id]

  def GetLineNumber(self, line_id):
    # type: (int) -> int
    return self.line_nums[line_id]

  # NOTE: Not used yet.  Using an intern table seems like a good idea, but I
  # haven't measured the performance benefit of it.  The case I'm thinking of
  # is where you have a tight loop and every line uses $LINENO.  It's better to
  # create 3 objects rather than 3*N objects, where N is the number of loop
  # iterations.
  def GetLineNumStr(self, line_id):
    # type: (int) -> str
    line_num = self.line_nums[line_id]
    s = self.line_num_strs.get(line_num)
    if s is None:
      s = str(line_num)
      self.line_num_strs[line_num] = s
    return s

  def GetCodeString(self, lbrace_spid, rbrace_spid):
    # type: (int, int) -> str
    left_span = self.GetToken(lbrace_spid)
    right_span = self.GetToken(rbrace_spid)

    assert self.line_srcs[left_span.line_id] == self.line_srcs[right_span.line_id]

    left_id = left_span.line_id
    right_id = right_span.line_id
    assert left_id <= right_id

    left_col = left_span.col  # 0-based indices
    right_col = right_span.col

    parts = []  # type: List[str]
    parts.append(' ' * (left_col+1))  # pad with spaces so column numbers are the same

    if left_id == right_id:
      # the single line
      parts.append(self.line_vals[left_id][left_col+1:right_col])
    else:
      # first incomplete line
      parts.append(self.line_vals[left_id][left_col+1:])

      # all the complete lines
      for line_id in xrange(left_id + 1, right_id):
        parts.append(self.line_vals[line_id])

      # last incomplete line
      parts.append(self.line_vals[right_id][:right_col])

    return ''.join(parts)

  def GetLineSource(self, line_id):
    # type: (int) -> source_t
    return self.line_srcs[line_id]

  def NewTokenId(self, id_, col, length, line_id, val):
    # type: (int, int, int, int, str) -> int
    span_id = len(self.tokens)  # spids are just array indices
    tok = Token(id_, col, length, line_id, span_id, val)
    self.tokens.append(tok)
    return span_id

  def NewToken(self, id_, col, length, line_id, val):
    # type: (int, int, int, int, str) -> Token
    span_id = self.NewTokenId(id_, col, length, line_id, val)
    return self.tokens[span_id]

  def GetToken(self, span_id):
    # type: (int) -> Token
    assert span_id != runtime.NO_SPID, span_id
    assert span_id < len(self.tokens), \
      'Span ID out of range: %d is greater than %d' % (span_id, len(self.tokens))
    return self.tokens[span_id]

  def LastSpanId(self):
    # type: () -> int
    """Return one past the last span ID."""
    return len(self.tokens)
