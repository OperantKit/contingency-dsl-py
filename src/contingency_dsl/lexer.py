"""Lexer for contingency-dsl: text -> token stream.

Two scanning modes share the same character-level rules:

* **Flat mode** — default. Whitespace and newlines are skipped; the
  output is a dense sequence of schedule/annotation tokens ending in EOF.
* **Block mode** — activated when the source contains a whole-word
  `phase`, `progressive`, or `shaping` keyword. Adds COLON/NEWLINE/GTE/
  PERCENT recognition and emits one NEWLINE token at the end of every
  non-blank logical line, so the parser can see phase/progressive/shaping
  block boundaries.

Indent-based INDENT/DEDENT emission is intentionally absent: every
experiment-layer block in the current grammar has a single level of
indentation and the outer structure is delimited by `phase`/`progressive`/
`shaping` keywords plus NEWLINE, so explicit INDENT/DEDENT tokens are not
required.
"""

from __future__ import annotations

import re

from .enums import (
    COMBINATOR_KEYWORDS,
    DR_KEYWORDS,
    EXPERIMENT_BLOCK_TRIGGERS,
    EXPERIMENT_LAYER_KEYWORDS,
    KW_ARG_KEYWORDS,
    LOWERCASE_RESERVED,
    SCHEDULE_TYPE_KEYWORDS,
    SPECIAL_KEYWORDS,
)
from .errors import LexError, SourceSpan
from .tokens import Token, TokenType


_BLOCK_TRIGGER_RE = re.compile(
    r"^[ \t]*(" + "|".join(sorted(EXPERIMENT_BLOCK_TRIGGERS)) + r")(?![A-Za-z0-9_])",
    re.MULTILINE,
)


def is_block_mode(source: str) -> bool:
    """Decide whether block-mode lexing should be applied to *source*.

    Block mode is triggered by a whole-word occurrence of any experiment-layer
    block starter (`phase`, `progressive`, `shaping`) that appears at the
    start of a logical line (after optional indentation). This matches their
    actual grammatical role and avoids mis-triggering on occurrences inside
    annotation keyword arguments like `@note(phase=1)`.
    """
    # Remove `--`-delimited line comments (the lexer also skips them).
    decommented = re.sub(r"--[^\n]*", "", source)
    # Strip string literals so that keyword-looking substrings inside a
    # string (e.g. annotation values) do not trigger block mode.
    stripped = re.sub(r'"[^"]*"', '""', decommented)
    return bool(_BLOCK_TRIGGER_RE.search(stripped))


def tokenize(source: str) -> list[Token]:
    """Tokenize DSL source text into a list of tokens."""
    block = is_block_mode(source)
    return _tokenize(source, block=block)


def _tokenize(source: str, *, block: bool) -> list[Token]:
    tokens: list[Token] = []
    lines = source.split("\n")
    # Paren-depth tracker for block mode: NEWLINE inside a balanced `(...)`
    # or `[...]` is suppressed so that multi-line compound expressions
    # (`Conc(VI60s,\n     VR20)`) parse as a single logical statement.
    paren_depth = 0

    for line_num, line_text in enumerate(lines, start=1):
        col = 0
        line_token_count_start = len(tokens)

        while col < len(line_text):
            ch = line_text[col]

            # Skip whitespace (indent is not yet tokenized as INDENT/DEDENT).
            if ch in (" ", "\t"):
                col += 1
                continue

            # Arrow: -> (directional keyword arg)
            if ch == "-" and col + 1 < len(line_text) and line_text[col + 1] == ">":
                tokens.append(Token(TokenType.ARROW, "->", line_num, col + 1))
                col += 2
                continue

            # Line comment: --
            if ch == "-" and col + 1 < len(line_text) and line_text[col + 1] == "-":
                break  # skip rest of line

            # >= (block-mode only; in flat mode, '>' is an unknown character
            # — matching the previous behavior)
            if block and ch == ">" and col + 1 < len(line_text) and line_text[col + 1] == "=":
                tokens.append(Token(TokenType.GTE, ">=", line_num, col + 1))
                col += 2
                continue

            # Punctuation
            if ch == "(":
                tokens.append(Token(TokenType.LPAREN, "(", line_num, col + 1))
                paren_depth += 1
                col += 1
                continue
            if ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")", line_num, col + 1))
                if paren_depth > 0:
                    paren_depth -= 1
                col += 1
                continue
            if ch == ",":
                tokens.append(Token(TokenType.COMMA, ",", line_num, col + 1))
                col += 1
                continue
            if ch == "=":
                tokens.append(Token(TokenType.EQUALS, "=", line_num, col + 1))
                col += 1
                continue
            if ch == "@":
                tokens.append(Token(TokenType.AT, "@", line_num, col + 1))
                col += 1
                continue
            if ch == "[":
                tokens.append(Token(TokenType.LBRACKET, "[", line_num, col + 1))
                paren_depth += 1
                col += 1
                continue
            if ch == "]":
                tokens.append(Token(TokenType.RBRACKET, "]", line_num, col + 1))
                if paren_depth > 0:
                    paren_depth -= 1
                col += 1
                continue
            # Dot: used only between identifiers (e.g. Pair.ForwardDelay).
            # Leading '.' for decimal numbers is handled by the number branch.
            if ch == "." and col + 1 < len(line_text) and line_text[col + 1].isalpha():
                tokens.append(Token(TokenType.DOT, ".", line_num, col + 1))
                col += 1
                continue
            if ch == "-" and col + 1 < len(line_text) and line_text[col + 1] not in ">":
                # Minus sign (for negative annotation values).
                # NOT "->" which is the ARROW token.
                tokens.append(Token(TokenType.MINUS, "-", line_num, col + 1))
                col += 1
                continue

            # Block-mode only characters
            if block and ch == ":":
                tokens.append(Token(TokenType.COLON, ":", line_num, col + 1))
                col += 1
                continue
            if block and ch == "%":
                tokens.append(Token(TokenType.PERCENT, "%", line_num, col + 1))
                col += 1
                continue
            # Placeholder `{ident}` (block mode only) or object literal
            # `{key=value, ...}` (any mode). The placeholder form is `{`
            # followed by alnum/underscore chars ending in `}` with nothing
            # else; anything else (including object literals with `=`) is
            # tokenised as LBRACE / RBRACE surrounding the contents so that
            # `@trial_mix(components=[{role="x", ref=0}, ...])` parses.
            if ch == "{":
                scan = col + 1
                while scan < len(line_text) and (
                    line_text[scan].isalnum() or line_text[scan] == "_"
                ):
                    scan += 1
                if (
                    block
                    and scan > col + 1
                    and scan < len(line_text)
                    and line_text[scan] == "}"
                ):
                    name = line_text[col + 1 : scan]
                    tokens.append(
                        Token(TokenType.PLACEHOLDER, name, line_num, col + 1)
                    )
                    col = scan + 1
                    col = _try_emit_time_unit(line_text, col, line_num, tokens)
                    continue
                tokens.append(Token(TokenType.LBRACE, "{", line_num, col + 1))
                paren_depth += 1
                col += 1
                continue
            if ch == "}":
                tokens.append(Token(TokenType.RBRACE, "}", line_num, col + 1))
                if paren_depth > 0:
                    paren_depth -= 1
                col += 1
                continue

            # String literal: "..."
            if ch == '"':
                start_col = col
                col += 1  # skip opening quote
                string_chars: list[str] = []
                while col < len(line_text) and line_text[col] != '"':
                    string_chars.append(line_text[col])
                    col += 1
                if col >= len(line_text):
                    raise LexError(
                        "unterminated string literal",
                        SourceSpan(line_num, start_col + 1),
                    )
                col += 1  # skip closing quote
                tokens.append(
                    Token(TokenType.STRING_LITERAL, "".join(string_chars), line_num, start_col + 1)
                )
                continue

            # Number (starts with digit or decimal point)
            if ch.isdigit() or (ch == "." and col + 1 < len(line_text) and line_text[col + 1].isdigit()):
                # Paper / phase label position: after a PHASE or EXPERIMENT
                # keyword token, admit digit-initial identifiers (`1`, `2a`,
                # `3_pilot`) per `schema/operant/grammar.ebnf` `digit_ident`.
                if (
                    block
                    and ch.isdigit()
                    and tokens
                    and tokens[-1].type in (TokenType.PHASE, TokenType.EXPERIMENT)
                ):
                    start_col = col
                    ident = ""
                    while col < len(line_text) and (
                        line_text[col].isalnum() or line_text[col] == "_"
                    ):
                        ident += line_text[col]
                        col += 1
                    tokens.append(
                        Token(TokenType.IDENTIFIER, ident, line_num, start_col + 1)
                    )
                    continue
                start_col = col
                num_str = ""
                while col < len(line_text) and (line_text[col].isdigit() or line_text[col] == "."):
                    num_str += line_text[col]
                    col += 1
                tokens.append(Token(TokenType.NUMBER, num_str, line_num, start_col + 1))
                col = _try_emit_time_unit(line_text, col, line_num, tokens)
                continue

            # Alphabetic word
            if ch.isalpha() or ch == "_":
                start_col = col
                word = ""
                while col < len(line_text) and (line_text[col].isalnum() or line_text[col] == "_"):
                    word += line_text[col]
                    col += 1

                token = _classify_word(word, line_num, start_col + 1, block=block)
                if token is not None:
                    tokens.append(token)
                    # If schedule type, check for immediately following number
                    if token.type == TokenType.SCHEDULE_TYPE:
                        keyword = word[:2]
                        rest = word[2:]
                        if rest:
                            tokens[-1] = Token(TokenType.SCHEDULE_TYPE, keyword, line_num, start_col + 1)
                            # Check for decimal continuation: FR5.0 -> word="FR5", then "." in source
                            decimal_extra = ""
                            if col < len(line_text) and line_text[col] == ".":
                                dc = col + 1
                                while dc < len(line_text) and line_text[dc].isdigit():
                                    dc += 1
                                if dc > col + 1:  # found digits after "."
                                    decimal_extra = line_text[col:dc]
                                    col = dc
                            _lex_number_suffix(rest + decimal_extra, tokens, line_num, start_col + 3)
                    elif token.type == TokenType.DR_MOD:
                        keyword = word[:3]
                        rest = word[3:]
                        if rest:
                            tokens[-1] = Token(TokenType.DR_MOD, keyword, line_num, start_col + 1)
                            _lex_number_suffix(rest, tokens, line_num, start_col + 4)
                    elif token.type == TokenType.LH:
                        # LH/LimitedHold followed by digits: LH10 -> LH + 10, LimitedHold10 -> LH + 10
                        prefix_len = 11 if word.startswith("LimitedHold") else 2
                        rest = word[prefix_len:]
                        if rest:
                            tokens[-1] = Token(TokenType.LH, word[:prefix_len], line_num, start_col + 1)
                            _lex_number_suffix(rest, tokens, line_num, start_col + prefix_len + 1)
                    elif token.type == TokenType.PR and len(word) > 2:
                        # PR2 / PR5 compact form → PR + number
                        tokens[-1] = Token(TokenType.PR, "PR", line_num, start_col + 1)
                        _lex_number_suffix(word[2:], tokens, line_num, start_col + 3)
                    continue
                # Should not reach here (all alpha words are classified)
                raise LexError(
                    f"unexpected word: '{word}'",
                    SourceSpan(line_num, start_col + 1, len(word)),
                )

            # Unknown character
            raise LexError(
                f"unexpected character: '{ch}'",
                SourceSpan(line_num, col + 1),
            )

        # End of logical line. In block mode, emit NEWLINE if the line
        # produced any tokens AND we are not inside a balanced `(...)` /
        # `[...]` pair — the latter suppresses NEWLINE so multi-line
        # compound expressions parse as a single statement.
        if (
            block
            and paren_depth == 0
            and len(tokens) > line_token_count_start
        ):
            tokens.append(Token(TokenType.NEWLINE, "\\n", line_num, len(line_text) + 1))

    # Strip a trailing NEWLINE before EOF (it adds no syntactic meaning).
    if tokens and tokens[-1].type == TokenType.NEWLINE:
        tokens.pop()

    tokens.append(Token(TokenType.EOF, "", len(lines), len(lines[-1]) + 1 if lines else 1))
    return tokens


def _try_emit_time_unit(
    line_text: str, col: int, line_num: int, tokens: list[Token]
) -> int:
    """Emit a TIME_UNIT token adjacent to the preceding NUMBER / PLACEHOLDER.

    Accepts the compact form (`60s`), hyphen-separated form (`60-s`, `60-min`,
    `60-sec`) and space-separated form (`60 s`, `60 min`, `60 sec`). The
    canonical value is always one of `"s"`, `"ms"`, `"min"`; `"sec"` is
    recognised as an alias for `"s"`. Returns the updated column cursor.
    """
    probe = col
    # Optional separator: a single `-` or one or more spaces/tabs between the
    # preceding numeric token and the unit. A hyphen followed by `>` is the
    # ARROW token and must not be consumed here.
    if probe < len(line_text) and line_text[probe] == "-":
        if probe + 1 < len(line_text) and line_text[probe + 1] == ">":
            return col
        probe += 1
    else:
        while probe < len(line_text) and line_text[probe] in (" ", "\t"):
            probe += 1
        if probe == col:
            # No separator — fall through to the adjacency rule below.
            pass
    remaining = line_text[probe:]
    if remaining.startswith("min"):
        end = probe + 3
        if end == len(line_text) or not (line_text[end].isalnum() or line_text[end] == "_"):
            tokens.append(Token(TokenType.TIME_UNIT, "min", line_num, probe + 1))
            return end
    if remaining.startswith("sec"):
        end = probe + 3
        if end == len(line_text) or not (line_text[end].isalnum() or line_text[end] == "_"):
            tokens.append(Token(TokenType.TIME_UNIT, "s", line_num, probe + 1))
            return end
    if remaining.startswith("ms"):
        end = probe + 2
        if end == len(line_text) or not line_text[end].isalpha():
            tokens.append(Token(TokenType.TIME_UNIT, "ms", line_num, probe + 1))
            return end
    if remaining.startswith("s") and (
        probe + 1 >= len(line_text) or not line_text[probe + 1].isalpha()
    ):
        tokens.append(Token(TokenType.TIME_UNIT, "s", line_num, probe + 1))
        return probe + 1
    return col


def _lex_number_suffix(rest: str, tokens: list[Token], line: int, col: int) -> None:
    """Lex a numeric suffix (e.g., '5', '60s', '3000ms') from a word tail."""
    # Split into number part and unit part
    i = 0
    while i < len(rest) and (rest[i].isdigit() or rest[i] == "."):
        i += 1
    num_part = rest[:i]
    unit_part = rest[i:]

    if num_part:
        tokens.append(Token(TokenType.NUMBER, num_part, line, col))
        col += len(num_part)

    if unit_part:
        if unit_part == "sec":
            tokens.append(Token(TokenType.TIME_UNIT, "s", line, col))
        elif unit_part in ("s", "ms", "min"):
            tokens.append(Token(TokenType.TIME_UNIT, unit_part, line, col))
        else:
            raise LexError(
                f"unrecognized time unit suffix: '{unit_part}' (expected 's', 'ms', or 'min')",
                SourceSpan(line, col, len(unit_part)),
            )


_EXPERIMENT_WORD_TO_TOKEN: dict[str, TokenType] = {
    "phase": TokenType.PHASE,
    "sessions": TokenType.SESSIONS,
    "stable": TokenType.STABLE,
    "use": TokenType.USE,
    "no_schedule": TokenType.NO_SCHEDULE,
    "shaping": TokenType.SHAPING,
    "progressive": TokenType.PROGRESSIVE,
    "steps": TokenType.STEPS,
    "interleave": TokenType.INTERLEAVE,
    "no_trailing": TokenType.NO_TRAILING,
    "advance": TokenType.ADVANCE,
    "when": TokenType.WHEN,
    "experiment": TokenType.EXPERIMENT,
}


def _classify_word(word: str, line: int, col: int, *, block: bool = False) -> Token | None:
    """Classify an alphabetic word into its token type."""
    # Experiment-layer keywords are only recognized in block mode; in flat
    # mode they fall through to IDENTIFIER to preserve backward compat.
    if block and word in _EXPERIMENT_WORD_TO_TOKEN:
        return Token(_EXPERIMENT_WORD_TO_TOKEN[word], word, line, col)

    # KW_ARG_KEYWORDS must be checked before SCHEDULE_TYPE to avoid
    # "FRCO" being split as schedule type "FR" + suffix "CO".
    if word in KW_ARG_KEYWORDS:
        return Token(TokenType.KW_ARG_NAME, word, line, col)

    # Check 2-char schedule type prefixes: word might be "FR", "FR5", "VI60s",
    # etc. Reject if the character right after the prefix is not a digit —
    # identifiers like `FI_Training` or `VIrtual` must not be mis-classified.
    if len(word) >= 2 and word[:2] in SCHEDULE_TYPE_KEYWORDS:
        if len(word) == 2 or word[2].isdigit():
            return Token(TokenType.SCHEDULE_TYPE, word, line, col)

    # 3-char DR modifiers: word might be "DRL", "DRL5s", etc. Same safeguard
    # as the schedule-type prefix check above.
    if len(word) >= 3 and word[:3] in DR_KEYWORDS:
        if len(word) == 3 or word[3].isdigit():
            return Token(TokenType.DR_MOD, word, line, col)

    # Exact keyword matches
    if word in SPECIAL_KEYWORDS:
        return Token(TokenType.EXT if word == "EXT" else TokenType.CRF, word, line, col)
    if word in COMBINATOR_KEYWORDS:
        return Token(TokenType.COMBINATOR, word, line, col)
    if len(word) >= 2 and word[:2] == "LH" and (len(word) == 2 or word[2].isdigit() or word[2] == "."):
        return Token(TokenType.LH, word, line, col)
    # LimitedHold alias: "LimitedHold", "LimitedHold10", "LimitedHold10s", etc.
    if len(word) >= 11 and word[:11] == "LimitedHold" and (len(word) == 11 or word[11].isdigit() or word[11] == "."):
        return Token(TokenType.LH, word, line, col)
    if word == "RD":
        return Token(TokenType.RD, word, line, col)
    if word == "ReinforcementDelay":
        return Token(TokenType.RD, word, line, col)
    if word == "PR":
        return Token(TokenType.PR, word, line, col)
    # Compact PR form: `PR2`, `PR5` → PR + number suffix (like DR_MOD).
    if len(word) >= 3 and word[:2] == "PR" and word[2].isdigit():
        return Token(TokenType.PR, word, line, col)
    if word == "Repeat":
        return Token(TokenType.REPEAT, word, line, col)
    if word == "let":
        return Token(TokenType.LET, word, line, col)
    if word in ("hodos", "linear", "exponential", "geometric", "uniform", "fixed"):
        return Token(TokenType.DISTRIBUTION_NAME, word, line, col)
    if word in ("start", "increment"):
        return Token(TokenType.PR_PARAM, word, line, col)

    # Identifier: must start with lowercase or underscore
    if word[0].islower() or word[0] == "_":
        if word in LOWERCASE_RESERVED:
            # Reserved words that are not keyword tokens (e.g., "def")
            # Still return as identifier — parser will reject if misused
            return Token(TokenType.IDENTIFIER, word, line, col)
        return Token(TokenType.IDENTIFIER, word, line, col)

    # Uppercase word that doesn't match any keyword
    return Token(TokenType.IDENTIFIER, word, line, col)
