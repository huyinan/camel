# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
# Licensed under the Apache License, Version 2.0 (the “License”);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an “AS IS” BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========

from typing import List, Optional

from camel.embeddings import BaseEmbedding, OpenAIEmbedding
from camel.memories import (
    AgentMemory,
    MemoryBlock,
    ChatHistoryMemory,
    ContextRecord,
    MemoryRecord,
)
from camel.memories.context_creators import BaseContextCreator, ScoreBasedContextCreator
from camel.storages.vectordb_storages import (
    BaseVectorStorage,
    QdrantStorage,
    VectorDBQuery,
    VectorRecord,
)
from camel.types import OpenAIBackendRole, ModelType


class VectorDBMemory(MemoryBlock):
    r"""An implementation of the :obj:`MemoryBlock` abstract base class for
    maintaining and retrieving information using vector embeddings within a
    vector database.

    Args:
        storage (Optional[BaseVectorStorage], optional): The storage mechanism
            for the vector database. Defaults to in-memory :obj:`Qdrant` if not
            provided. (default: :obj:`None`)
        embedding (Optional[BaseEmbedding], optional): Embedding mechanism to
            convert chat messages into vector representations. Defaults to
            :obj:`OpenAiEmbedding` if not provided. (default: :obj:`None`)
    """

    def __init__(
        self,
        storage: Optional[BaseVectorStorage] = None,
        embedding: Optional[BaseEmbedding] = None,
    ) -> None:
        self.embedding = embedding or OpenAIEmbedding()
        self.vector_dim = self.embedding.get_output_dim()
        self.storage = storage or QdrantStorage(vector_dim=self.vector_dim)

    def retrieve(
        self,
        keyword: str,
        limit: int = 3,
    ) -> List[ContextRecord]:
        r"""Retrieves similar records from the vector database based on the
        content of the keyword.

        Args:
            keyword (str): This string will be converted into a vector
                representation to query the database.
            limit (int, optional): The maximum number of similar messages to
                retrieve. (default: :obj:`3`).

        Returns:
            List[MemoryRecord]: A list of memory records retrieved from the
                vector database based on similarity to :obj:`current_state`.
        """
        query_vector = self.embedding.embed(keyword)
        results = self.storage.query(VectorDBQuery(query_vector, top_k=limit))
        return [
            ContextRecord(
                memory_record=MemoryRecord.from_dict(result.record.payload),
                score=result.similarity,
            ) for result in results if result.record.payload is not None
        ]

    def write_records(self, records: List[MemoryRecord]) -> None:
        """
        Converts the provided chat messages into vector representations and
        writes them to the vector database.

        Args:
            msgs (List[BaseMessage]): Messages to be added to the vector
                database.
        """
        v_records = [
            VectorRecord(
                vector=self.embedding.embed(record.message.content),
                payload=record.to_dict(),
                id=str(record.uuid),
            ) for record in records
        ]
        self.storage.add(v_records)

    def clear(self) -> None:
        r"""Removes all records from the vector database memory."""
        self.storage.clear()


class VectorDBAgentMemory(VectorDBMemory, AgentMemory):
    r""""""

    def __init__(
        self,
        context_creator: BaseContextCreator,
        storage: Optional[BaseVectorStorage] = None,
    ) -> None:
        self._context_creator = context_creator
        self._current_topic: Optional[str] = None
        super().__init__(storage=storage)

    def retrieve(self) -> List[ContextRecord]:
        return super().retrieve(self._current_topic, limit=3)

    def write_records(self, records: List[MemoryRecord]) -> None:
        for record in records:
            if record.role_at_backend == OpenAIBackendRole.USER:
                self._current_topic = record.message.content
        super().write_records(records)

    def get_context_creator(self) -> BaseContextCreator:
        return self._context_creator
