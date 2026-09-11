"""Model selection and request serialization checks without provider calls."""

import base64
import importlib.util
import json
import os
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("nebula-image2-1k", "nebula-image2-4k", "nebula-nanobanana")
PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


class ModelSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runners = {}
        for name in SKILLS:
            path = ROOT / "skills" / name / "scripts" / "generate_image.py"
            spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            cls.runners[name] = (runner, runner.load_config())

    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def resolve(self, runner, config, options=(), reference_count=0):
        args = runner.build_parser(config).parse_args(["--prompt", "test prompt", *options])
        return args, runner.resolve_settings(config, args, reference_count)

    def test_defaults_and_blank_environment_fallback(self):
        for name, (runner, config) in self.runners.items():
            for value in (None, "", " \t "):
                with self.subTest(skill=name, environment=value):
                    os.environ.pop(config["model_env"], None)
                    if value is not None:
                        os.environ[config["model_env"]] = value
                    _, settings = self.resolve(runner, config)
                    self.assertEqual(settings["model"], config["model"])

    def test_environment_and_command_line_precedence(self):
        for name, (runner, config) in self.runners.items():
            with self.subTest(skill=name):
                env_model = "gpt-image-2.5-sunburst" if config["transport"] == "images" else config["models"][1]
                cli_model = "gpt-image-2.5-flare" if config["transport"] == "images" else config["models"][2]
                os.environ[config["model_env"]] = f" {env_model}\t"
                _, settings = self.resolve(runner, config)
                self.assertEqual(settings["model"], env_model)
                _, settings = self.resolve(runner, config, ["--model", f" {cli_model} "])
                self.assertEqual(settings["model"], cli_model)

    def test_images_blank_command_line_falls_back(self):
        for name in SKILLS[:2]:
            runner, config = self.runners[name]
            for cli_value in ("", " \t "):
                for env_value in ("", "gpt-image-2.5-flare"):
                    with self.subTest(skill=name, cli=cli_value, environment=env_value):
                        os.environ[config["model_env"]] = env_value
                        _, settings = self.resolve(runner, config, ["--model", cli_value])
                        self.assertEqual(settings["model"], env_value or config["model"])

    def test_model_environment_variables_are_isolated(self):
        os.environ["APINEBULA_IMAGE2_4K_MODEL"] = "gpt-image-2.5-sunburst"
        for name in ("nebula-image2-1k", "nebula-nanobanana"):
            with self.subTest(skill=name):
                runner, config = self.runners[name]
                _, settings = self.resolve(runner, config)
                self.assertEqual(settings["model"], config["model"])

    def test_images_default_is_read_from_config(self):
        for name in SKILLS[:2]:
            with self.subTest(skill=name):
                runner, config = self.runners[name]
                _, settings = self.resolve(runner, {**config, "model": "future-default-model"})
                self.assertEqual(settings["model"], "future-default-model")

    def test_images_override_reaches_requests_and_result_metadata(self):
        reference = {"buffer": base64.b64decode(PNG_BASE64), "filename": "input.png", "mime_type": "image/png"}
        response = {"data": [{"b64_json": PNG_BASE64}]}
        with tempfile.TemporaryDirectory() as output:
            for name in SKILLS[:2]:
                runner, config = self.runners[name]
                for model in ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "future-compatible-model"):
                    for edit in (False, True):
                        with self.subTest(skill=name, model=model, edit=edit):
                            options = ["--model", model, "--output", str(Path(output) / "result.png")]
                            args, settings = self.resolve(runner, config, options, int(edit))
                            references = [reference] if edit else []
                            with patch.object(runner, "read_json_response", return_value=response) as send:
                                result = runner.call_provider(config, settings, args.prompt, references, "test-key")
                            request = send.call_args.args[0]
                            if edit:
                                headers = f"Content-Type: {request.get_header('Content-type')}\r\n\r\n".encode("ascii")
                                message = BytesParser(policy=policy.default).parsebytes(headers + request.data)
                                fields = {
                                    part.get_param("name", header="content-disposition"): part.get_payload(decode=True).decode("utf-8")
                                    for part in message.iter_parts() if not part.get_filename()
                                }
                            else:
                                fields = json.loads(request.data)
                            suffix = "/v1/images/edits" if edit else "/v1/images/generations"
                            self.assertTrue(request.full_url.endswith(suffix))
                            self.assertEqual(fields["model"], model)
                            section = config["editing" if edit else "generation"]
                            self.assertEqual(fields["size"], section["default_size"])
                            self.assertEqual(runner.dry_run_summary(settings, args.prompt)["model"], model)
                            saved = runner.save_result(config, settings, args.prompt, result, args, "test-key")
                            metadata = json.loads(Path(saved["metadata_path"]).read_text(encoding="utf-8"))
                            self.assertEqual(saved["model"], model)
                            self.assertEqual(metadata["apinebula_skill"]["model"], model)

    def test_gemini_override_and_resolution_validation(self):
        runner, config = self.runners["nebula-nanobanana"]
        os.environ[config["model_env"]] = "gemini-3-pro-image-preview"
        args, settings = self.resolve(runner, config, ["--resolution", "4K"])
        with patch.object(runner, "read_json_response", return_value={}) as send:
            runner.call_provider(config, settings, args.prompt, [], "test-key")
        request = send.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/v1beta/models/gemini-3-pro-image-preview:generateContent"))
        self.assertEqual(json.loads(request.data)["generationConfig"]["imageConfig"]["imageSize"], "4K")
        os.environ[config["model_env"]] = "gemini-2.5-flash-image"
        with self.assertRaisesRegex(runner.SkillError, "supports only 1K"):
            self.resolve(runner, config, ["--resolution", "4K"])
        os.environ[config["model_env"]] = "unknown-gemini-model"
        with self.assertRaisesRegex(runner.SkillError, "not supported"):
            self.resolve(runner, config)


if __name__ == "__main__":
    unittest.main()
