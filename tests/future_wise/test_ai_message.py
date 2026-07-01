from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.ai_services.providers import AzureOpenAIProvider, OpenAIProvider, get_ai_providers
from apps.future_wise.services.ai_message import AIMessageGenerationError, generate_reminder_message


class _FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def generate(self, system_prompt, user_prompt):
        if self.error:
            raise self.error
        return self.response


class AIMessageServiceTest(SimpleTestCase):
    @patch("apps.future_wise.services.ai_message.get_ai_providers")
    def test_generate_reminder_message_returns_structured_content(self, mock_get_providers):
        mock_get_providers.return_value = [
            (
                "openai",
                _FakeProvider(
                    response=(
                        "```json\n"
                        '{"subject":"Birthday wishes","email_body":"Happy birthday!","short_message":"Have a great day!","call_script":"Hello and happy birthday!"}\n'
                        "```"
                    )
                ),
            )
        ]

        result = generate_reminder_message(
            letter_type="birthday_wish",
            occasion="Birthday",
            tone="warm",
            recipient_name="Ava",
            language="English",
            channels=["email", "voice_call"],
            extra_context="Mention the family dinner.",
        )

        self.assertEqual(result["subject"], "Birthday wishes")
        self.assertEqual(result["email_body"], "Happy birthday!")
        self.assertEqual(result["short_message"], "Have a great day!")
        self.assertEqual(result["call_script"], "Hello and happy birthday!")

    @patch("apps.future_wise.services.ai_message.get_ai_providers")
    def test_generate_reminder_message_clears_call_script_without_voice_channel(self, mock_get_providers):
        mock_get_providers.return_value = [
            (
                "openai",
                _FakeProvider(
                    response=(
                        '{"subject":"Renew soon","email_body":"Your plan renews tomorrow.",'
                        '"short_message":"Reminder: your plan renews tomorrow.","call_script":"Voice content"}'
                    )
                ),
            )
        ]

        result = generate_reminder_message(
            letter_type="subscription_renewal_reminder",
            channels=["email", "sms"],
        )

        self.assertEqual(result["call_script"], "")

    @patch("apps.future_wise.services.ai_message.get_ai_providers")
    def test_generate_reminder_message_tries_fallback_provider(self, mock_get_providers):
        mock_get_providers.return_value = [
            ("gemini", _FakeProvider(error=RuntimeError("boom"))),
            (
                "openai",
                _FakeProvider(
                    response=(
                        '{"subject":"Meeting reminder","email_body":"See you tomorrow.",'
                        '"short_message":"Meeting tomorrow.","call_script":"See you tomorrow."}'
                    )
                ),
            ),
        ]

        result = generate_reminder_message(letter_type="meeting_reminder", channels=["voice"])

        self.assertEqual(result["subject"], "Meeting reminder")
        self.assertEqual(result["call_script"], "See you tomorrow.")

    @override_settings(DEBUG=True)
    @patch("apps.future_wise.services.ai_message.get_ai_providers", return_value=[])
    def test_generate_reminder_message_raises_clear_error_without_provider(self, mock_get_providers):
        with self.assertRaises(AIMessageGenerationError) as exc:
            generate_reminder_message(letter_type="custom_message")

        self.assertEqual(
            str(exc.exception),
            "AI message generation is currently unavailable. Please write your message manually.",
        )
        mock_get_providers.assert_called_once()


class AIProviderConfigurationTest(SimpleTestCase):
    @override_settings(OPENAI_API_KEY="")
    def test_openai_provider_requires_api_key(self):
        with self.assertRaises(RuntimeError) as exc:
            OpenAIProvider()

        self.assertEqual(str(exc.exception), "OpenAI is not configured. Set OPENAI_API_KEY.")

    @override_settings(OPENAI_API_KEY="test-openai-key", AI_MODEL="gpt-test-model")
    @patch("openai.OpenAI")
    def test_openai_provider_generate_uses_client(self, mock_openai):
        mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Generated text"))]
        )

        provider = OpenAIProvider()
        result = provider.generate("system", "user")

        self.assertEqual(result, "Generated text")
        mock_openai.return_value.chat.completions.create.assert_called_once()

    @override_settings(AZURE_OPENAI_API_KEY="", AZURE_OPENAI_ENDPOINT="")
    def test_azure_openai_provider_requires_credentials(self):
        with self.assertRaises(RuntimeError) as exc:
            AzureOpenAIProvider()

        self.assertEqual(
            str(exc.exception),
            "Azure OpenAI is not configured. Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT.",
        )

    @override_settings(
        AZURE_OPENAI_API_KEY="test-azure-key",
        AZURE_OPENAI_ENDPOINT="https://azure.example.com",
        AZURE_OPENAI_API_VERSION="2024-10-21",
        AI_MODEL="gpt-test-model",
    )
    @patch("openai.AzureOpenAI")
    def test_azure_openai_provider_generate_uses_client(self, mock_azure_openai):
        mock_azure_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Azure generated text"))]
        )

        provider = AzureOpenAIProvider()
        result = provider.generate("system", "user")

        self.assertEqual(result, "Azure generated text")
        mock_azure_openai.return_value.chat.completions.create.assert_called_once()

    @override_settings(AI_PROVIDER_FALLBACKS="openai,azure_openai,gemini")
    @patch("apps.ai_services.providers.OpenAIProvider", return_value="openai-provider")
    @patch("apps.ai_services.providers.AzureOpenAIProvider", side_effect=RuntimeError("missing azure"))
    @patch("apps.ai_services.providers.GeminiProvider", return_value="gemini-provider")
    def test_get_ai_providers_returns_available_fallbacks(self, mock_gemini, mock_azure, mock_openai):
        providers = get_ai_providers()

        self.assertEqual(providers, [("openai", "openai-provider"), ("gemini", "gemini-provider")])
        mock_openai.assert_called_once()
        mock_azure.assert_called_once()
        mock_gemini.assert_called_once()
