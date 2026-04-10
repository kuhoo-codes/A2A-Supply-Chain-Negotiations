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

            return _parse_json_response(output_text)
        except OpenAIDecisionError:
            raise
        except json.JSONDecodeError as exc:
            raise OpenAIDecisionError("OpenAI returned invalid JSON.") from exc
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise OpenAIDecisionError(
                f"OpenAI decision call failed: {detail}"
            ) from exc


def _parse_json_response(output_text: str) -> dict:
    cleaned_output = output_text.strip()
    if not cleaned_output:
        raise OpenAIDecisionError("OpenAI returned an empty decision response.")

    try:
        return json.loads(cleaned_output)
    except json.JSONDecodeError:
        pass

    if cleaned_output.startswith("```"):
        lines = cleaned_output.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            fenced_payload = "\n".join(lines[1:-1]).strip()
            if fenced_payload.lower().startswith("json"):
                fenced_payload = fenced_payload[4:].strip()
            return json.loads(fenced_payload)

    first_brace = cleaned_output.find("{")
    last_brace = cleaned_output.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        return json.loads(cleaned_output[first_brace : last_brace + 1])

    raise OpenAIDecisionError("OpenAI returned invalid JSON.")
