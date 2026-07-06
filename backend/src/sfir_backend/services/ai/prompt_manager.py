"""Prompt template management and intent classification.

Separates prompt construction from LLM invocation, allowing
prompt templates to be versioned and audited independently.
"""

from enum import Enum
from typing import Any

import structlog

from sfir_backend.infrastructure.llm.base import LLMPrompt

logger = structlog.get_logger(__name__)


class Intent(str, Enum):
    METADATA_SEARCH = "metadata_search"
    METADATA_EXPLANATION = "metadata_explanation"
    IMPACT_ANALYSIS = "impact_analysis"
    DOCUMENTATION_GENERATION = "documentation_generation"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    ACTION_PLANNING = "action_planning"
    DEPLOYMENT_SUMMARY = "deployment_summary"
    RELEASE_NOTES = "release_notes"
    FIELD_DOCUMENTATION = "field_documentation"
    OBJECT_DOCUMENTATION = "object_documentation"
    AUTOMATION_EXPLANATION = "automation_explanation"
    PERMISSION_EXPLANATION = "permission_explanation"
    MIGRATION_PLANNING = "migration_planning"
    RISK_SCORING = "risk_scoring"
    GENERAL_QUESTION = "general_question"


SYSTEM_PROMPTS: dict[Intent, str] = {
    Intent.METADATA_SEARCH: (
        "You are a Salesforce metadata expert. Given a natural language query, "
        "identify the relevant Salesforce metadata components (objects, fields, "
        "relationships, flows, apex, validation rules) and explain how they "
        "relate to the user's question. Always reference specific API names. "
        "If metadata is not available in the provided context, say so clearly."
    ),
    Intent.METADATA_EXPLANATION: (
        "You are a Salesforce metadata expert. Explain the purpose, usage, and "
        "configuration of the provided metadata component. Include field types, "
        "relationships, dependencies, and any automation that references it. "
        "Always cite the specific metadata that supports your explanation."
    ),
    Intent.IMPACT_ANALYSIS: (
        "You are a Salesforce change impact analyst. Given a proposed change "
        "to a metadata component, analyze the full impact. Identify all "
        "components that would be affected, assess risk level, and provide "
        "a detailed summary. Never speculate about components not present in "
        "the dependency data provided."
    ),
    Intent.DOCUMENTATION_GENERATION: (
        "You are a Salesforce technical writer. Generate comprehensive, "
        "professional documentation for the given metadata component. Include "
        "purpose, fields/attributes, relationships, dependencies, and usage notes. "
        "Format in Markdown with clear sections."
    ),
    Intent.DEPENDENCY_ANALYSIS: (
        "You are a Salesforce dependency graph expert. Analyze the dependency "
        "relationships for the given component. Explain what depends on it, "
        "what it depends on, and the nature of each dependency. Highlight "
        "critical dependencies that could cause issues if changed."
    ),
    Intent.ACTION_PLANNING: (
        "You are a Salesforce DevOps engineer. Given a user's request to modify "
        "Salesforce metadata, create a detailed step-by-step action plan. "
        "Include: what will change, the deployment order, validation steps, "
        "rollback plan, and risk assessment. Never suggest direct modification "
        "without proper safety validation."
    ),
    Intent.DEPLOYMENT_SUMMARY: (
        "You are a Salesforce release manager. Summarize the deployment, "
        "highlighting key changes, affected components, risk areas, and "
        "verification results. Provide a clear go/no-go recommendation."
    ),
    Intent.RELEASE_NOTES: (
        "You are a Salesforce release note writer. Generate clear, "
        "user-friendly release notes from the deployment data. "
        "Group changes by type (new, modified, removed) and component type. "
        "Use business-friendly language without losing technical accuracy."
    ),
    Intent.FIELD_DOCUMENTATION: (
        "You are a Salesforce data steward. Document the given field with its "
        "data type, dependencies, usage in automations, picklist values, and "
        "relationship to other objects. Include business context suggestions."
    ),
    Intent.OBJECT_DOCUMENTATION: (
        "You are a Salesforce data architect. Document the given object with "
        "all its fields, relationships, automation references, security settings, "
        "and usage patterns. Format as comprehensive reference documentation."
    ),
    Intent.AUTOMATION_EXPLANATION: (
        "You are a Salesforce automation expert. Explain how the given Flow, "
        "Process Builder, or Apex Trigger works. Describe the trigger conditions, "
        "decision logic, actions performed, and fields modified. Reference the "
        "actual metadata elements involved."
    ),
    Intent.PERMISSION_EXPLANATION: (
        "You are a Salesforce security analyst. Explain the access permissions "
        "for the given object or field. Detail which profiles and permission "
        "sets grant access, the level of access (CRUD/FLS), and any sharing "
        "rules that apply."
    ),
    Intent.MIGRATION_PLANNING: (
        "You are a Salesforce migration architect. Analyze the provided metadata "
        "and create a migration plan. Consider dependencies, order of operations, "
        "data mapping, validation strategy, and rollback planning."
    ),
    Intent.RISK_SCORING: (
        "You are a Salesforce risk assessment analyst. Evaluate the risk of "
        "modifying the given component based on its dependency graph. Consider: "
        "number of dependents, criticality of dependents, deployment history, "
        "and automation references. Provide a risk score (0-100) and mitigation "
        "recommendations."
    ),
    Intent.GENERAL_QUESTION: (
        "You are a Salesforce AI assistant with deep knowledge of Salesforce "
        "metadata, architecture, and best practices. Answer the user's question "
        "based on the metadata context provided. If the answer requires "
        "information not in the provided context, say so and suggest how the "
        "user could find that information."
    ),
}


class PromptManager:
    """Manages prompt templates and builds LLM prompts for different intents."""

    def __init__(self, templates: dict[Intent, str] | None = None) -> None:
        self._templates = templates or SYSTEM_PROMPTS

    def classify_intent(self, query: str) -> Intent:
        """Classify the user query into an intent.

        Uses keyword matching for now. Can be replaced with an LLM-based
        classifier for more accuracy.
        """
        query_lower = query.lower()

        intent_keywords: list[tuple[list[str], Intent]] = [
            (["document", "field documentation", "object documentation", "generate docs"],
             Intent.DOCUMENTATION_GENERATION),
            (["impact", "what breaks", "what happens if", "change impact", "affect"],
             Intent.IMPACT_ANALYSIS),
            (["where is", "find", "search", "metadata search", "what uses"],
             Intent.METADATA_SEARCH),
            (["explain", "what is", "describe", "how does", "tell me about"],
             Intent.METADATA_EXPLANATION),
            (["dependency", "what depends", "what references", "who uses"],
             Intent.DEPENDENCY_ANALYSIS),
            (["plan", "action plan", "steps to", "how to modify", "create field", "add field"],
             Intent.ACTION_PLANNING),
            (["deployment summary", "deploy result", "release notes"],
             Intent.DEPLOYMENT_SUMMARY),
            (["release notes", "what changed"],
             Intent.RELEASE_NOTES),
            (["flow explain", "automation", "how does this flow", "trigger explain"],
             Intent.AUTOMATION_EXPLANATION),
            (["permission", "who can access", "profile access", "fls"],
             Intent.PERMISSION_EXPLANATION),
            (["migration", "migrate", "move metadata"],
             Intent.MIGRATION_PLANNING),
            (["risk", "risk score", "how risky"],
             Intent.RISK_SCORING),
        ]

        for keywords, intent in intent_keywords:
            if any(kw in query_lower for kw in keywords):
                return intent

        return Intent.GENERAL_QUESTION

    def build_prompt(
        self,
        intent: Intent,
        user_query: str,
        context: str = "",
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float = 0.1,
    ) -> LLMPrompt:
        """Build a complete LLM prompt from intent and context."""
        system_prompt = self._templates.get(intent, self._templates[Intent.GENERAL_QUESTION])

        if context:
            system_prompt += (
                "\n\n--- METADATA CONTEXT ---\n"
                f"{context}\n"
                "--- END CONTEXT ---\n\n"
                "Use the metadata context above to answer. "
                "If the context does not contain the needed information, "
                "say so instead of fabricating answers."
            )

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_query})

        return LLMPrompt(
            system_prompt=system_prompt,
            messages=messages,
            temperature=temperature,
        )

    def add_template(self, intent: Intent, template: str) -> None:
        """Add or override a prompt template."""
        self._templates[intent] = template
        logger.info("prompt_template_updated", intent=intent.value)
