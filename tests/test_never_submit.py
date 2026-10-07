"""The apply step must never submit. These checks fail the build if the fill script ever gains a way to."""
import re
import subprocess
import unittest
from pathlib import Path

APPLY = Path(__file__).resolve().parent.parent / "apply"


def code(name):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", (APPLY / name).read_text(), flags=re.S)  # comments may name them


CODE = code("fill.mjs") + code("workday.mjs")
GUARD = code("guard.mjs")


class NeverSubmit(unittest.TestCase):
    def test_clicks_only_go_through_the_guard(self):
        # fill.mjs and workday.mjs may click only via safeClick(); the one raw .click( lives in guard.mjs
        for pat in [r"\.click\(", r"\.dblclick\(", r"\.press\((?!'Escape'\))", r"\.tap\(", r"\.submit\(",
                    r"requestSubmit", r"keyboard\.(?!press\('Escape'\))", r"mouse\.", r"dispatchEvent",
                    r"\.check\(", r"'Enter'"]:
            self.assertIsNone(re.search(pat, CODE), f"fill.mjs/workday.mjs must not contain {pat}")
        self.assertEqual(len(re.findall(r"\.click\(", GUARD)), 1)

    def test_guard_refuses_submit_and_allows_the_flow(self):
        js = """
        import { mayClick } from './apply/guard.mjs';
        const no = [
          [{text: 'Submit'}, 'button'], [{text: 'Submit Application'}, 'button'],
          [{text: 'Save and Continue', aid: 'submitButton'}, 'button'], [{text: 'Sign In'}, 'button'],
          [{text: 'Create Account'}, 'button'], [{label: 'I agree to the terms'}, 'radio'],
          [{text: 'Accept'}, 'option'], [{text: 'Next', type: 'submit', label: 'Submit'}, 'button'],
          [{text: 'Delete'}, 'button'], [{text: 'Withdraw'}, 'button'], [{text: 'Send'}, 'button'],
          [{text: 'Random Button'}, 'button'],
        ];
        const yes = [
          [{text: 'Apply'}, 'button'], [{text: 'Autofill with Resume'}, 'button'],
          [{text: 'Save and Continue'}, 'button'], [{text: 'Next'}, 'button'], [{text: 'Yes'}, 'radio'],
          [{text: 'Mobile'}, 'option'], [{text: 'Select One', label: 'Phone Device Type'}, 'listbox'],
        ];
        const bad = no.filter(([i, k]) => mayClick(i, k)).concat(yes.filter(([i, k]) => !mayClick(i, k)));
        console.log(JSON.stringify(bad));
        """
        out = subprocess.run(["node", "--input-type=module", "-e", js], cwd=APPLY.parent,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout.strip(), "[]", out.stderr or out.stdout)

    def test_only_value_setters_touch_the_page(self):
        calls = set(re.findall(r"\.(fill|selectOption|setInputFiles|type|goto)\(", CODE))
        self.assertLessEqual(calls, {"fill", "selectOption", "setInputFiles", "goto"})


if __name__ == "__main__":
    unittest.main()
