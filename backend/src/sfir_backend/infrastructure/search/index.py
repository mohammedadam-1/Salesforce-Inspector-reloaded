from __future__ import annotations

import re
from collections import defaultdict

from sfir_backend.domain.search.models import SearchDocument


def tokenize(text: str) -> list[str]:
    text = text.lower().strip()
    tokens: list[str] = []
    for part in re.split(r"[^a-zA-Z0-9_.*?\-]+", text):
        part = part.strip()
        if part:
            tokens.append(part)
            sub_parts = part.split(".")
            for i in range(1, len(sub_parts)):
                tokens.append(".".join(sub_parts[:i]))
    return tokens


def tokenize_for_prefix(text: str) -> list[str]:
    text = text.lower().strip()
    tokens: list[str] = []
    for part in re.split(r"[^a-zA-Z0-9_.\-]+", text):
        part = part.strip()
        if part:
            tokens.append(part)
            parts = part.split(".")
            for i in range(1, len(parts)):
                tokens.append(".".join(parts[:i]))
    return tokens


class InvertedIndex:
    def __init__(self) -> None:
        self._postings: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set),
        )
        self._all_docs: set[str] = set()

    def index_document(
        self,
        doc_id: str,
        text: str,
        field: str = "default",
    ) -> None:
        self._all_docs.add(doc_id)
        for token in tokenize(text):
            self._postings[field][token].add(doc_id)

    def index_document_raw(
        self,
        doc_id: str,
        tokens: list[str],
        field: str = "default",
    ) -> None:
        self._all_docs.add(doc_id)
        for token in tokens:
            self._postings[field][token].add(doc_id)

    def search_term(self, term: str, field: str | None = None) -> set[str]:
        term = term.lower()
        if field:
            return set(self._postings[field].get(term, set()))
        result: set[str] = set()
        for f in self._postings:
            if term in self._postings[f]:
                result.update(self._postings[f][term])
        return result

    def search_prefix(self, prefix: str, field: str | None = None) -> set[str]:
        prefix = prefix.lower()
        result: set[str] = set()
        fields = [field] if field else list(self._postings.keys())
        for f in fields:
            for term, doc_ids in self._postings[f].items():
                if term.startswith(prefix):
                    result.update(doc_ids)
        return result

    def search_suffix(self, suffix: str, field: str | None = None) -> set[str]:
        suffix = suffix.lower()
        result: set[str] = set()
        fields = [field] if field else list(self._postings.keys())
        for f in fields:
            for term, doc_ids in self._postings[f].items():
                if term.endswith(suffix):
                    result.update(doc_ids)
        return result

    def search_wildcard(self, pattern: str, field: str | None = None) -> set[str]:
        pattern = pattern.lower().replace("*", ".*").replace("?", ".")
        try:
            regex = re.compile(f"^{pattern}$")
        except re.error:
            return set()
        result: set[str] = set()
        fields = [field] if field else list(self._postings.keys())
        for f in fields:
            for term, doc_ids in self._postings[f].items():
                if regex.search(term):
                    result.update(doc_ids)
        return result

    def all_documents(self) -> set[str]:
        return set(self._all_docs)

    def clear(self) -> None:
        self._postings.clear()
        self._all_docs.clear()

    @property
    def total_terms(self) -> int:
        seen: set[str] = set()
        for field_dict in self._postings.values():
            seen.update(field_dict.keys())
        return len(seen)

    @property
    def total_documents(self) -> int:
        return len(self._all_docs)


class PrefixTrie:
    class Node:
        def __init__(self) -> None:
            self.children: dict[str, PrefixTrie.Node] = {}
            self.terms: list[str] = []

    def __init__(self) -> None:
        self._root = self.Node()

    def insert(self, term: str) -> None:
        node = self._root
        for ch in term.lower():
            if ch not in node.children:
                node.children[ch] = self.Node()
            node = node.children[ch]
        if term not in node.terms:
            node.terms.append(term)

    def _find_node(self, prefix: str) -> Node | None:
        node = self._root
        for ch in prefix.lower():
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node

    def _collect_terms(self, node: Node, limit: int) -> list[str]:
        result: list[str] = []
        stack = [node]
        while stack and len(result) < limit:
            current = stack.pop()
            for term in current.terms:
                if len(result) >= limit:
                    break
                if term not in result:
                    result.append(term)
            for ch in sorted(current.children.keys(), reverse=True):
                stack.append(current.children[ch])
        return result

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        node = self._find_node(prefix)
        if node is None:
            return []
        return self._collect_terms(node, limit)

    def clear(self) -> None:
        self._root = self.Node()


class SearchIndex:
    def __init__(self) -> None:
        self._inverted = InvertedIndex()
        self._prefix_trie = PrefixTrie()
        self._documents: dict[str, SearchDocument] = {}
        self._by_type: dict[str, set[str]] = defaultdict(set)
        self._by_org: dict[str, set[str]] = defaultdict(set)
        self._by_namespace: dict[str, set[str]] = defaultdict(set)

    def index_document(self, doc: SearchDocument) -> None:
        self._documents[doc.id] = doc
        self._by_type[doc.metadata_type].add(doc.id)
        self._by_org[doc.organization_id].add(doc.id)
        if doc.namespace:
            self._by_namespace[doc.namespace].add(doc.id)

        text = doc.searchable_text()
        self._inverted.index_document(doc.id, text, "default")
        self._inverted.index_document(doc.id, doc.api_name, "api_name")
        self._inverted.index_document(doc.id, doc.label, "label")
        if doc.description:
            self._inverted.index_document(doc.id, doc.description, "description")
        if doc.namespace:
            self._inverted.index_document(doc.id, doc.namespace, "namespace")

        for token in tokenize_for_prefix(doc.api_name):
            self._prefix_trie.insert(token)
        for token in tokenize_for_prefix(doc.label):
            self._prefix_trie.insert(token)

    def get_document(self, doc_id: str) -> SearchDocument | None:
        return self._documents.get(doc_id)

    def search(self, query_tokens: list[str], operator: str = "AND") -> set[str]:
        if not query_tokens:
            return self._inverted.all_documents()
        token_results: list[set[str]] = []
        for token in query_tokens:
            result: set[str] = set()
            if token.startswith("*") and token.endswith("*"):
                result = self._inverted.search_wildcard(token.strip("*"))
            elif token.startswith("*"):
                result = self._inverted.search_suffix(token.lstrip("*"))
            elif token.endswith("*"):
                result = self._inverted.search_prefix(token.rstrip("*"))
            elif "?" in token or "*" in token:
                result = self._inverted.search_wildcard(token)
            else:
                result = self._inverted.search_term(token)
                if len(token) >= 2:
                    result |= self._inverted.search_prefix(token)
            token_results.append(result)
        if not token_results:
            return set()
        if operator == "AND":
            result = token_results[0].copy()
            for r in token_results[1:]:
                result &= r
            return result
        result = set()
        for r in token_results:
            result |= r
        return result

    def search_by_type(self, metadata_type: str) -> list[SearchDocument]:
        doc_ids = self._by_type.get(metadata_type, set())
        return [self._documents[did] for did in doc_ids if did in self._documents]

    def search_by_org(self, org_id: str) -> set[str]:
        return set(self._by_org.get(org_id, set()))

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        return self._prefix_trie.suggest(prefix, limit)

    def count_by_type(self) -> dict[str, int]:
        return {t: len(ids) for t, ids in self._by_type.items()}

    @property
    def total_documents(self) -> int:
        return len(self._documents)

    def clear(self) -> None:
        self._inverted.clear()
        self._prefix_trie.clear()
        self._documents.clear()
        self._by_type.clear()
        self._by_org.clear()
        self._by_namespace.clear()
