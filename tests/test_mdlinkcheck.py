"""Tests for mdlinkcheck. Stdlib only, no network, no files outside a temporary directory."""
import contextlib
import io
import os
import tempfile
import textwrap
import unittest

import mdlinkcheck


def write(content: str, name: str = "doc.md") -> str:
    """Write `content` into a fresh temporary directory and return the file's path."""
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(content).lstrip("\n"))
    return path


class TargetsAreFiltered(unittest.TestCase):
    def test_a_present_relative_link_is_not_reported(self):
        path = write(
            """
            # Title
            [ok](README.md)
            """
        )
        open(os.path.join(os.path.dirname(path), "README.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_external_shapes_are_skipped(self):
        path = write(
            """
            [a](https://example.com/x)
            [b](http://example.com/x)
            [c](mailto:someone@example.com)
            [d](tel:+1234567890)
            [e](#a-heading)
            [f](//example.com/x)
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_broken_targets_are_reported_with_their_line_numbers(self):
        path = write(
            """
            # Title

            [one](missing-one.md)
            [two](missing-two.md)
            """
        )
        self.assertEqual(
            mdlinkcheck.check_file(path),
            [(3, "missing-one.md"), (4, "missing-two.md")],
        )

    def test_image_targets_are_checked_too(self):
        path = write(
            """
            ![alt](missing.png)
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [(1, "missing.png")])

    def test_a_fragment_or_query_is_stripped_before_the_check(self):
        path = write(
            """
            [heading](README.md#a-heading)
            [query](README.md?v=2)
            """
        )
        open(os.path.join(os.path.dirname(path), "README.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_a_directory_target_counts_as_satisfied(self):
        path = write(
            """
            [folder](subdir)
            """
        )
        os.mkdir(os.path.join(os.path.dirname(path), "subdir"))
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_targets_resolve_against_the_file_not_the_working_directory(self):
        path = write(
            """
            [ok](README.md)
            """
        )
        open(os.path.join(os.path.dirname(path), "README.md"), "w").close()
        cwd = os.getcwd()
        os.chdir(tempfile.gettempdir())
        try:
            self.assertEqual(mdlinkcheck.check_file(path), [])
        finally:
            os.chdir(cwd)

    def test_link_syntax_inside_an_inline_code_span_is_not_a_link(self):
        path = write(
            """
            It parses `[text](target)` and `![alt](target)`.
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_link_syntax_inside_a_fenced_block_is_not_a_link(self):
        path = write(
            """
            ```markdown
            [text](target)
            ```

            [real](missing.md)
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [(5, "missing.md")])

    def test_a_reference_definition_is_checked_on_its_own_line(self):
        path = write(
            """
            # Title

            [the docs][docs]
            [gone][gone]

            [docs]: README.md
            [gone]: missing.md
            """
        )
        open(os.path.join(os.path.dirname(path), "README.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [(7, "missing.md")])

    def test_a_reference_definition_inside_a_list_item_is_checked(self):
        path = write(
            """
            - [one](missing-one.md)
            - [two](missing-two.md)
            """
        )
        self.assertEqual(
            mdlinkcheck.check_file(path),
            [(1, "missing-one.md"), (2, "missing-two.md")],
        )

    def test_parentheses_inside_a_target_do_not_end_it(self):
        path = write(
            """
            [ok](file(1).md)
            [broken](nope(2).md)
            """
        )
        open(os.path.join(os.path.dirname(path), "file(1).md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [(2, "nope(2).md")])

    def test_a_percent_encoded_target_is_decoded_before_the_check(self):
        path = write(
            """
            [ok](a%20b.md)
            """
        )
        open(os.path.join(os.path.dirname(path), "a b.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_a_wrapped_target_with_spaces_is_read_whole(self):
        path = write(
            """
            [ok](<a b.md>)
            [broken](<no such file.md>)
            """
        )
        open(os.path.join(os.path.dirname(path), "a b.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [(2, "no such file.md")])

    def test_an_escaped_paren_is_a_real_paren_in_the_path(self):
        path = write(
            """
            [ok](a\\).md)
            """
        )
        open(os.path.join(os.path.dirname(path), "a).md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_a_linked_image_checks_its_outer_target_too(self):
        path = write(
            """
            # Title

            [![badge](img.png)](MISSING.md)
            """
        )
        open(os.path.join(os.path.dirname(path), "img.png"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [(3, "MISSING.md")])

    def test_a_linked_image_reports_the_image_when_only_it_is_missing(self):
        path = write(
            """
            [![badge](missing.png)](README.md)
            """
        )
        open(os.path.join(os.path.dirname(path), "README.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [(1, "missing.png")])

    def test_a_linked_image_with_both_targets_present_is_not_reported(self):
        path = write(
            """
            [![badge](img.png)](README.md)
            """
        )
        directory = os.path.dirname(path)
        open(os.path.join(directory, "img.png"), "w").close()
        open(os.path.join(directory, "README.md"), "w").close()
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_a_linked_image_reports_both_targets_when_both_are_missing(self):
        path = write(
            """
            [![badge](missing.png)](MISSING.md)
            """
        )
        self.assertEqual(
            mdlinkcheck.check_file(path),
            # `check_file` sorts its findings, so the two line 1 targets come back ASCII order.
            [(1, "MISSING.md"), (1, "missing.png")],
        )

    def test_a_target_reachable_twice_by_nesting_is_reported_once(self):
        path = write(
            """
            [a [b](missing.md) and more](missing.md)
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [(1, "missing.md")])

    def test_an_escaped_bracket_does_not_open_a_label(self):
        path = write(
            """
            An escaped \\[bracket](missing.md) is text, not a link.
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [])

    def test_a_broken_reported_target_is_the_decoded_path(self):
        path = write(
            """
            [broken](no%20such%20file.md)
            """
        )
        self.assertEqual(mdlinkcheck.check_file(path), [(1, "no such file.md")])


class CommandLine(unittest.TestCase):
    def test_a_clean_file_exits_zero(self):
        path = write(
            """
            [ok](https://example.com)
            """
        )
        self.assertEqual(mdlinkcheck.main([path]), 0)

    def test_a_broken_link_exits_one_and_names_the_line(self):
        path = write(
            """
            # Title

            [broken](missing.md)
            """
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = mdlinkcheck.main([path])
        self.assertEqual(code, 1)
        self.assertEqual(
            buffer.getvalue().strip(),
            f"{path}:3: broken link: missing.md",
        )

    def test_quiet_prints_nothing_and_still_exits_one(self):
        path = write(
            """
            [broken](missing.md)
            """
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = mdlinkcheck.main([path, "--quiet"])
        self.assertEqual(code, 1)
        self.assertEqual(buffer.getvalue(), "")

    def test_an_unreadable_file_is_reported_and_fails(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = mdlinkcheck.main(["does-not-exist.md"])
        self.assertEqual(code, 1)
        self.assertIn("cannot read", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
