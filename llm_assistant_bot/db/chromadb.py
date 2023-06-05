import time

import chromadb
from chromadb.utils import embedding_functions


from ..config import Config
from ..utils.get_random_hex import get_random_hex

from chromadb.config import Settings
client = chromadb.Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory=Config.chromadb.persist_directory,
))
chromadb_client = client


def get_embedding_function():
    function_type = Config.chromadb.embedding_function_type
    model_name = Config.chromadb.embedding_function_model_name
    if function_type == 'openai':
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=Config.openai_api_key,
            model_name=model_name,
        )
    else:
        raise NotImplementedError(f'embedding_function_type: {function_type}')


def get_memory_collection():
    return client.get_or_create_collection(
        name="memory",
        embedding_function=get_embedding_function()
    )


def add_memory(text_list):
    if not isinstance(text_list, list):
        text_list = [text_list]
    timestamp = get_current_timestamp()
    ids = []
    metadatas = []

    for _ in text_list:
        ids.append(get_random_hex())
        metadatas.append({'created_at': timestamp})

    memory_collection = get_memory_collection()
    memory_collection.add(
        documents=text_list,
        ids=ids,
        metadatas=metadatas,
    )
    client.persist()


def query_memory(query_list, n_results=10):
    if not isinstance(query_list, list):
        query_list = [query_list]

    memory_collection = get_memory_collection()
    if memory_collection.count() <= 0:
        return []

    results = memory_collection.query(
        query_texts=query_list,
        n_results=n_results,
    )

    return [
        {
            'id': doc_id,
            'document': document,
            'metadata': metadata,
            'distance': distance,
        }
        for doc_id, document, metadata, distance
        in zip(
            results['ids'][0],
            (results['documents'] or [])[0],
            (results['metadatas'] or [])[0],
            (results['distances'] or [])[0],
        )
    ]


def delete_memory(ids):
    if not isinstance(ids, list):
        ids = [ids]

    memory_collection = get_memory_collection()
    memory_collection.delete(ids=ids)
    client.persist()


def get_current_timestamp():
    return int(time.time())


def get_docs_collection():
    return client.get_or_create_collection(
        name="docs",
        embedding_function=get_embedding_function()
    )


def add_docs(type_, docs):
    timestamp = get_current_timestamp()
    text_list = []
    ids = []
    metadatas = []

    for d in docs:
        ids.append(get_random_hex())
        text_list.append(d.page_content)
        metadatas.append({
            **d.metadata,
            '_type': type_,
            'saved_at': timestamp,
        })

    docs_collection = get_docs_collection()
    docs_collection.add(
        documents=text_list,
        ids=ids,
        metadatas=metadatas,
    )
    client.persist()


def query_docs(query_list, n_results=10):
    if not isinstance(query_list, list):
        query_list = [query_list]

    docs_collection = get_docs_collection()
    if docs_collection.count() <= 0:
        return []

    results = docs_collection.query(
        query_texts=query_list,
        n_results=n_results,
    )

    return [
        {
            'id': doc_id,
            'document': document,
            'metadata': metadata,
            'distance': distance,
        }
        for doc_id, document, metadata, distance
        in zip(
            results['ids'][0],
            (results['documents'] or [])[0],
            (results['metadatas'] or [])[0],
            (results['distances'] or [])[0],
        )
    ]


def delete_docs_by_type(type_):
    docs_collection = get_docs_collection()
    docs_collection.delete(
        where={'_type': type_}
    )
    client.persist()
