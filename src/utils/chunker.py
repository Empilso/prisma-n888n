def chunk_records(records: list, max_tokens_per_chunk: int = 2000) -> list:
    """
    Divide lista de registros em chunks que não excedem max_tokens_per_chunk.
    Cada registro é uma linha da tabela.
    """
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for record in records:
        record_tokens = len(record) // 4
        
        if current_tokens + record_tokens > max_tokens_per_chunk and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [record]
            current_tokens = record_tokens
        else:
            current_chunk.append(record)
            current_tokens += record_tokens
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks
