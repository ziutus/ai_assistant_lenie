

const ListItemSearchSimilar = ({ item }) => {
    return (
        <li>
            {item.similarity} {item.id} - {item.text}

            ({item.website_id})
            <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.url}
            </a>

            {/* <button onClick={() => handleDeleteLink(item.id)}>
        Delete
      </button> */}
        </li>
    )
}


export default ListItemSearchSimilar
