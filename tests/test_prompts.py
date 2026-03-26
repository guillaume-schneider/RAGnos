from __future__ import annotations

import unittest

from tests.test_support import workspace_tempdir, write_prompt

from ragnos.prompts import build_prompt, load_prompt_text


class PromptTests(unittest.TestCase):
    def test_load_prompt_text_reads_plain_utf8_text(self) -> None:
        with workspace_tempdir() as root:
            prompt_path = write_prompt(root)
            prompt_text = load_prompt_text(prompt_path)

        self.assertIn("{context}", prompt_text)

    def test_build_prompt_interpolates_context_and_input(self) -> None:
        prompt = build_prompt("Contexte:\n{context}")
        rendered = prompt.invoke({"context": "ARTICLE 1", "input": "Question ?"})

        self.assertIn("ARTICLE 1", rendered.messages[0].content)
        self.assertEqual(rendered.messages[1].content, "Question ?")
