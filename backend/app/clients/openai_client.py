import json

from backend.app.core.config import Settings


class OpenAIDecisionError(Exception):
    pass


class OpenAIClientWrapper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_status(self) -> tuple[bool, bool, str]:
        if not self.settings.openai_enabled:
            return False, False, "OPENAI_API_KEY is not configured."

        try:
            from openai import OpenAI  # noqa: F401
        except ImportError:
            return True, False, "OpenAI package is not installed."

        return True, True, f"Configured with model {self.settings.openai_model}."

    def decide_action(self, prompt: str) -> dict:
        configured, available, _ = self.get_status()
        if not configured or not available:
            raise OpenAIDecisionError("OpenAI is not configured or available.")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.settings.openai_api_key)
            response = client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
            )
            output_text = getattr(response, "output_text", "")
            if not output_text:
                raise OpenAIDecisionError("OpenAI returned an empty decision response.")

            return json.loads(output_text)
        except OpenAIDecisionError:
            raise
        except json.JSONDecodeError as exc:
            raise OpenAIDecisionError("OpenAI returned invalid JSON.") from exc
        except Exception as exc:
            raise OpenAIDecisionError("OpenAI decision call failed.") from exc
