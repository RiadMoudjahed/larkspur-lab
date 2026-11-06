"""The CLI must explain itself, since people install it without seeing the repository."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from larkspur import __version__
from larkspur.cli import main


def run(*argv, **env):
    out = io.StringIO()
    with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
        main(list(argv))
    return out.getvalue()


class TestHelp(unittest.TestCase):
    def test_no_arguments_prints_the_guide(self):
        text = run()
        for expected in ("C1", "C2", "C3", "ollama pull", "larkspur chat", "WRITEUP.md"):
            self.assertIn(expected, text)

    def test_version(self):
        with self.assertRaises(SystemExit) as caught:
            run("--version")
        self.assertEqual(caught.exception.code, 0)
        self.assertTrue(__version__)


class TestModelErrors(unittest.TestCase):
    def test_unreachable_model_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"LARKSPUR_DB": f"{tmp}/l.db", "LARKSPUR_BASE_URL": "http://127.0.0.1:9/v1"}
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
                with mock.patch.dict(os.environ, env):
                    main(["triage"])
        self.assertIn("ollama pull", str(caught.exception.code))


class TestProgress(unittest.TestCase):
    def test_database_is_created_under_home(self):
        with tempfile.TemporaryDirectory() as home:
            env = {"HOME": home, "USERPROFILE": home}
            with mock.patch.dict(os.environ, env):
                os.environ.pop("LARKSPUR_DB", None)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    main(["check"])
            self.assertTrue(os.path.exists(os.path.join(home, ".larkspur", "larkspur.db")))
            self.assertIn("C1 [open]", out.getvalue())


if __name__ == "__main__":
    unittest.main()
