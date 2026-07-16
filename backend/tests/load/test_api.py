# ────────────────────────────────────────────────────────────
# SFIR Backend — API Load Tests (locustfile)
# Run: locust -f tests/load/test_api.py --host=https://api.sfir.dev
# ────────────────────────────────────────────────────────────

import random
import uuid

from locust import FastHttpUser, between, task


class APIUser(FastHttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.token = None
        self.org_id = None

    @task(5)
    def health_check(self) -> None:
        self.client.get("/api/v1/health/live")

    @task(3)
    def health_ready(self) -> None:
        self.client.get("/api/v1/health/ready")

    @task(10)
    def list_providers(self) -> None:
        self.client.get("/api/v1/ai/providers")

    @task(5)
    def list_tools(self) -> None:
        self.client.get("/api/v1/ai/tools")


class AuthenticatedAPIUser(FastHttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self) -> None:
        self.token = f"test-token-{uuid.uuid4()}"
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def get_version(self) -> None:
        self.client.get("/api/v1/version", headers=self.headers)

    @task(2)
    def get_security_status(self) -> None:
        self.client.get("/api/v1/security/status", headers=self.headers)

    @task(1)
    def get_usage(self) -> None:
        self.client.get("/api/v1/ai/usage", headers=self.headers)


class MetadataSearchUser(FastHttpUser):
    wait_time = between(2.0, 5.0)

    def on_start(self) -> None:
        self.token = f"search-token-{uuid.uuid4()}"
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.queries = [
            "Account",
            "Contact",
            "Opportunity",
            "ApexClass",
            "ValidationRule",
            "Flow",
            "PermissionSet",
            "Profile",
            "Dashboard",
            "Report",
        ]

    @task(5)
    def search(self) -> None:
        query = random.choice(self.queries)
        self.client.get(
            "/api/v1/search",
            params={"query": query, "limit": 20},
            headers=self.headers,
        )

    @task(2)
    def autocomplete(self) -> None:
        query = random.choice(self.queries)[:3]
        self.client.get(
            "/api/v1/search/autocomplete",
            params={"prefix": query, "limit": 10},
            headers=self.headers,
        )


class AIQueryUser(FastHttpUser):
    wait_time = between(3.0, 8.0)

    def on_start(self) -> None:
        self.token = f"ai-token-{uuid.uuid4()}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.queries = [
            "What metadata components does Account use?",
            "Explain this Apex class structure",
            "Summarize the dependency graph",
            "Generate release notes for the latest changes",
            "What is the impact of modifying the Account object?",
        ]

    @task(3)
    def ai_query(self) -> None:
        query = random.choice(self.queries)
        self.client.post(
            "/api/v1/ai/query",
            json={"query": query},
            headers=self.headers,
        )
