interface ListItemSearchSimilarProps {
  item: {
    similarity: number;
    id: number;
    text: string;
    website_id: number;
    url: string;
  };
}

const ListItemSearchSimilar = ({ item }: ListItemSearchSimilarProps) => {
    return (
        <li>
            {item.similarity} {item.id} - {item.text}

            ({item.website_id})
            <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.url}
            </a>
        </li>
    )
}


export default ListItemSearchSimilar
