interface ListItemSearchSimilarProps {
  item: {
    similarity: number;
    id: number;
    text: string;
    website_id: number;
    url: string;
    chunk_id?: number | null;
    obsidian_note_paths?: string[];
  };
}

const ListItemSearchSimilar = ({ item }: ListItemSearchSimilarProps) => {
    const notes = item.obsidian_note_paths ?? [];
    return (
        <li>
            {item.similarity} {item.id} - {item.text}

            ({item.website_id})
            <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.url}
            </a>
            {item.chunk_id != null && (
                <>
                    {" "}
                    <a href={`/chunks/${item.website_id}`}>chunk #{item.chunk_id}</a>
                </>
            )}
            {notes.length > 0 && (
                <span title={notes.join("\n")}> 📝 {notes.length}</span>
            )}
        </li>
    )
}


export default ListItemSearchSimilar
