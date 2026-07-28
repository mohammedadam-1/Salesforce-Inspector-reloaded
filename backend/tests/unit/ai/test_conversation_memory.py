import uuid
from sfir_backend.domain.ai.models import AIFeature
from sfir_backend.infrastructure.llm.conversation_memory import ConversationMemory


class TestConversationMemory:
    def setup_method(self) -> None:
        self.memory = ConversationMemory(max_conversations=10)

    def test_create_conversation(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        conv = self.memory.create_conversation(
            organization_id=org_id,
            user_id=user_id,
            title="Test",
            feature=AIFeature.QUESTION_ANSWERING,
        )
        assert conv.title == "Test"
        assert conv.organization_id == org_id
        assert conv.user_id == user_id

    def test_get_conversation(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        conv = self.memory.create_conversation(org_id, user_id)
        retrieved = self.memory.get_conversation(conv.conversation_id)
        assert retrieved is not None
        assert retrieved.conversation_id == conv.conversation_id

    def test_get_conversation_missing(self) -> None:
        assert self.memory.get_conversation(uuid.uuid4()) is None

    def test_add_message(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        conv = self.memory.create_conversation(org_id, user_id)
        msg = self.memory.add_message(conv.conversation_id, "user", "Hello")
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_add_message_to_nonexistent(self) -> None:
        result = self.memory.add_message(uuid.uuid4(), "user", "test")
        assert result is None

    def test_get_history(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        conv = self.memory.create_conversation(org_id, user_id)
        self.memory.add_message(conv.conversation_id, "user", "Hi")
        self.memory.add_message(conv.conversation_id, "assistant", "Hello!")
        history = self.memory.get_history(conv.conversation_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["content"] == "Hello!"

    def test_list_conversations(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        self.memory.create_conversation(org_id, user_id, title="Conv1")
        self.memory.create_conversation(org_id, user_id, title="Conv2")
        convs = self.memory.list_conversations(organization_id=org_id)
        assert len(convs) == 2

    def test_list_conversations_filtered_by_user(self) -> None:
        org_id = uuid.uuid4()
        user1 = uuid.uuid4()
        user2 = uuid.uuid4()
        self.memory.create_conversation(org_id, user1, title="U1")
        self.memory.create_conversation(org_id, user2, title="U2")
        convs = self.memory.list_conversations(user_id=user1)
        assert len(convs) == 1

    def test_delete_conversation(self) -> None:
        org_id = uuid.uuid4()
        conv = self.memory.create_conversation(org_id, uuid.uuid4())
        assert self.memory.delete_conversation(conv.conversation_id) is True
        assert self.memory.get_conversation(conv.conversation_id) is None

    def test_delete_nonexistent(self) -> None:
        assert self.memory.delete_conversation(uuid.uuid4()) is False

    def test_enforce_limit(self) -> None:
        memory = ConversationMemory(max_conversations=2)
        org_id = uuid.uuid4()
        memory.create_conversation(org_id, uuid.uuid4())
        memory.create_conversation(org_id, uuid.uuid4())
        memory.create_conversation(org_id, uuid.uuid4())
        assert len(memory._conversations) <= 2
