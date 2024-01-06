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

from pathlib import Path
from typing import Any, List, Optional, Tuple, Union
from urllib.parse import urlparse

from camel.embeddings import BaseEmbedding, OpenAIEmbedding
from camel.functions import OpenAIFunction
from camel.functions.unstructured_io_fuctions import UnstructuredModules
from camel.storages.vectordb_storages import (
    BaseVectorStorage,
    QdrantStorage,
    VectorDBQuery,
    VectorRecord,
)

DEFAULT_TOP_K_RESULTS = 1
DEFAULT_SIMILARITY_THRESTOLD = 0.75


class RetrievalModule:
    r"""Implements retrieval by combining vector storage with an embedding model.

    This class facilitates the retrieval of relevant information using a
    query-based approach, backed by vector embeddings.

    Attributes:
        embedding_model (BaseEmbedding): Embedding model used to generate
        vector embeddings.
    """

    def __init__(self,
                 embedding_model: Optional[BaseEmbedding] = None) -> None:
        r"""Initializes the retrieval class with an optional embedding model
        and vector storage, and sets the number of top results for retrieval.

        Args:
            embedding_model (Optional[BaseEmbedding]): The embedding model
            instance. Defaults to `OpenAIEmbedding` if not provided.
        """
        self.embedding_model = embedding_model or OpenAIEmbedding()
        self.vector_dim = self.embedding_model.get_output_dim()

    def _initialize_qdrant_storage(
        self,
        collection_name: Optional[str] = None,
        is_collection_accessible: Optional[bool] = None,
        vector_storage_local_path: Optional[str] = None,
        url_and_api_key: Optional[Tuple[str, str]] = None,
    ) -> QdrantStorage:
        r"""Sets up and returns a `Qdrant` storage instance with specified parameters.

        Args:
            collection_name (Optional[str]): Name of the collection in the
            vector storage.
            is_collection_accessible (Optional[bool]): Flag indicating if the
            collection already exists.
            vector_storage_local_path (Optional[str]): Filesystem path for
            local vector storage.
            url_and_api_key (Optional[Tuple[str, str]]): URL and API key for
            remote storage access.

        Returns:
            QdrantStorage: Configured Qdrant storage instance.
        """

        return QdrantStorage(vector_dim=self.vector_dim,
                             collection=collection_name,
                             create_collection=not is_collection_accessible,
                             path=vector_storage_local_path,
                             url_and_api_key=url_and_api_key)

    def _check_qdrant_collection_status(
            self, collection_name: str,
            vector_storage_local_path: Optional[str] = None,
            url_and_api_key: Optional[Tuple[str, str]] = None) -> bool:
        r"""Checks and returns the status of the specified collection in the
        `Qdrant` storage.

        Args:
            collection_name (str): Name of the collection to check.
            vector_storage_local_path (Optional[str]): Filesystem path for
            local vector storage (used when storage_type is 'local').
            url_and_api_key (Optional[Tuple[str, str]]): URL and API key for
            remote storage access (used when storage_type is 'remote').

        Returns:
            bool: True if the collection exists and is accessible, False
            otherwise.
        """
        try:
            storage = QdrantStorage(vector_dim=self.vector_dim,
                                    collection=collection_name,
                                    path=vector_storage_local_path,
                                    url_and_api_key=url_and_api_key)

            storage.status
            return True

        except Exception:
            return False

    def embed_and_store_chunks(self, content_input_path: str,
                               vector_storage: BaseVectorStorage,
                               **kwargs: Any) -> None:
        r""" Processes content from a file or URL, divides it into chunks by
        using `Unstructured IO`, and stores their embeddings in the specified
        vector storage.

        Args:
            content_input_path (str): File path or URL of the content to be
            processed.
            vector_storage (BaseVectorStorage): Vector storage to store the
            embeddings.
            **kwargs (Any): Additional keyword arguments for elements chunking.
        """
        unstructured_modules = UnstructuredModules()
        elements = unstructured_modules.parse_file_or_url(content_input_path)
        chunks = unstructured_modules.chunk_elements(
            chunk_type="chunk_by_title", elements=elements, **kwargs)

        for chunk in chunks:
            # Get vector from chunk string
            vector = self.embedding_model.embed(obj=str(chunk))
            # Get content path, metadata, text
            content_path_info = {"content path": content_input_path}
            chunk_metadata = {"metadata": chunk.metadata.to_dict()}
            chunk_text = {"text": str(chunk)}
            # Combine the information into one dict as payload
            combined_dict = {
                **content_path_info,
                **chunk_metadata,
                **chunk_text
            }
            vector_storage.add(
                records=[VectorRecord(vector=vector, payload=combined_dict)])

    def query_and_compile_results(
            self, query: str, vector_storage: BaseVectorStorage,
            top_k: int = DEFAULT_TOP_K_RESULTS,
            similarity_threshold: float = DEFAULT_SIMILARITY_THRESTOLD,
            **kwargs: Any) -> str:
        r"""Executes a query in vector storage and compiles the retrieved
        results into a string.

        Args:
            query (str): Query string for information retrieval.
            vector_storage (BaseVectorStorage): Vector storage to query.
            top_k (int, optional): The number of top results to return during
            retrieval. Must be a positive integer. Defaults to 1.
            similarity_threshold (float, optional): The similarity threshold
            for filtering results. Defaults to 0.75.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            str: Concatenated string of the query results.

        Raises:
            ValueError: If 'top_k' is less than or equal to 0.
        """
        if top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        query_vector = self.embedding_model.embed(obj=query)
        db_query = VectorDBQuery(query_vector=query_vector, top_k=top_k)
        query_results = vector_storage.query(query=db_query, **kwargs)
        # format the results
        formatted_results = []
        for result in query_results:
            if (result.similarity >= similarity_threshold
                    and result.record.payload is not None):
                result_dict = {
                    'similarity score': str(result.similarity),
                    'content path':
                    result.record.payload.get('content path', ''),
                    'metadata': result.record.payload.get('metadata', {}),
                    'text': result.record.payload.get('text', '')
                }
                formatted_results.append(str(result_dict))

        if (not formatted_results
                and query_results[0].record.payload is not None):
            return f"""No suitable information retrieved from
            {query_results[0].record.payload.get('content path','')} with
            similarity_threshold = {similarity_threshold}."""
        return "\n".join(formatted_results)

    def run_default_retrieval(
            self, query: str, content_input_paths: Union[str, list[str]],
            vector_storage_local_path: Optional[str] = None,
            url_and_api_key: Optional[Tuple[str, str]] = None) -> str:
        r"""Executes the default retrieval process using `Qdrant` storage.

        Args:
            query (str): Query string for information retrieval.
            content_input_paths (Union[str, list[str]]): Paths to content
            files or URLs.
            vector_storage_local_path (Optional[str]): Local path for `Qdrant`
            storage.
            url_and_api_key (Optional[Tuple[str, str]]): URL and API key for
            `Qddrant` storage remote access.

        Returns:
            str: Aggregated information retrieved in response to the query.

        Raises:
            RuntimeError: If any errors occur during the retrieval process.
        """

        content_input_paths = [content_input_paths] if isinstance(
            content_input_paths, str) else content_input_paths

        retrieved_infos = ""

        for content_input_path in content_input_paths:
            # Check path type
            parsed_url = urlparse(content_input_path)
            is_url = all([parsed_url.scheme, parsed_url.netloc])
            # Convert given path into collection name
            collection_name = (content_input_path.replace(
                "https://", "").replace("/", "_").strip("_") if is_url else
                               Path(content_input_path).stem.replace(' ', '_'))

            is_collection_accessible = self._check_qdrant_collection_status(
                vector_storage_local_path=vector_storage_local_path,
                url_and_api_key=url_and_api_key,
                collection_name=collection_name)

            try:
                vector_storage_instance = self._initialize_qdrant_storage(
                    collection_name=collection_name,
                    is_collection_accessible=is_collection_accessible,
                    vector_storage_local_path=vector_storage_local_path,
                    url_and_api_key=url_and_api_key)

                if not is_collection_accessible:
                    self.embed_and_store_chunks(content_input_path,
                                                vector_storage_instance)

                retrieved_info = self.query_and_compile_results(
                    query, vector_storage_instance)
                retrieved_infos += "\n" + retrieved_info
                output = ("Original Query:" + "\n" + "{" + query + "}" + "\n" +
                          "Retrieved Context:" + retrieved_infos)
            except Exception as e:
                raise RuntimeError(
                    f"Error in retrieval processing: {str(e)}") from e

        return output


def local_retrieval(query: str) -> str:
    r"""Performs a default local retrieval for information. Given a query,
    this function will retrieve the information from the local vector storage,
    and return the retrieved information back. It is useful for information
    retrieval.

    Args:
        query (string): Question you want to be answered.

    Returns:
        str: Aggregated information retrieved in response to the query.
    """
    retrieval_instance = RetrievalModule()
    retrieved_info = retrieval_instance.run_default_retrieval(
        content_input_paths=[
            "https://www.camel-ai.org/",
        ], vector_storage_local_path="examples/rag/", query=query)
    return retrieved_info


def remote_retrieval(query: str) -> str:
    r"""Performs a default remote retrieval for information. Given a query,
    this function will retrieve the information from the remote vector
    storage, and return the retrieved information back. It is useful for
    information retrieval.

    Args:
        query (string): Question you want to be answered.

    Returns:
        str: Aggregated information retrieved in response to the query.
    """
    retrieval_instance = RetrievalModule()
    retrieved_info = retrieval_instance.run_default_retrieval(
        content_input_paths=[
            "https://www.camel-ai.org/",
        ], url_and_api_key=(
            "https://c7ac871b-0dca-4586-8b03-9ffb4e40363e."
            "us-east4-0.gcp.cloud.qdrant.io:6333",
            "axny37nzYHwg8jxbW-TnC90p8MibC1Tl4ypSwM87boZhSqvedvW_7w"),
        query=query)
    return retrieved_info


RETRIEVAL_FUNCS: List[OpenAIFunction] = [
    OpenAIFunction(func) for func in [local_retrieval, remote_retrieval]
]
