import './App.css';
import axios from 'axios';
import React, { useState } from 'react';

function App() {

    const [apiUrl, setApiUrl] = useState("https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1");
    const [apiKey, setApiKey] = useState('');
    const [linkUrl, setLinkUrl] = useState('');
    const [documentType, setDocumentType] = useState('webpage');
    const [message, setMessage] = useState('');
    const [source, setSource] = useState('');
    const [chapterList, setChapterList] = useState('');
    const [language, setLanguage] = useState('pl');
    const [makeAISummary, setMakeAISummary] = useState(false);
    const [note, setNote] = useState('');
    const [text, setText] = useState('');


    React.useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const apikeyParam = params.get('apikey');

        if (apikeyParam) {
            setApiKey(apikeyParam);
        }
    }, []);

    const handleClean = () => {
        setLinkUrl("")
        setDocumentType('webpage')
        setSource("")
        setChapterList("")
        setLanguage('pl')
        setMakeAISummary(false)
        setNote('')
        setText('')
    }

    const handleSaveWebsite = async () => {

        try {
            const response = await axios.post(`${apiUrl}/url_add`, {
                url: linkUrl   ,
                type: documentType,
                source: source,
                chapterList: chapterList,
                language: language,
                makeAISummary: makeAISummary,
                text: text,
                note: note
            }, {
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': `${apiKey}`,

                },
            });
            handleClean()
            setMessage(response.data);
            // console.log(response.data.message);
            // console.log(response.data)

        } catch (error) {
            console.error("There was an error saving the data!", error);
            setMessage('There was an error saving the data.');
        }
    };


  return (
    <div className="App">
        <header className="App-header">
            <h1>Lenie</h1>
            <div>Adding link to queue</div>
            <div>
                <label>
                    Serwer API:
                    <input type="text" value={apiUrl} onChange={e => setApiUrl(e.target.value)}
                           style={{width: '20ch'}}/>
                </label>
            </div>
            <div>
                <label>
                    API Key:
                    <input type="text" value={apiKey} onChange={e => setApiKey(e.target.value)}
                           style={{width: '40ch'}}/>
                </label>
            </div>
            <div>
                <label>
                    Link:
                    <input type="text" value={linkUrl} onChange={e => setLinkUrl(e.target.value)}
                           style={{width: '150ch'}}/>
                </label>
            </div>
            <div>
                <label>
                    Document Type:
                    <select value={documentType} onChange={e => setDocumentType(e.target.value)}>
                        <option value="link">Link</option>
                        <option value="webpage">Webpage</option>
                        <option value="youtube">Youtube</option>
                        <option value="movie">Movie</option>
                        <option value="text_message">Text message</option>
                    </select>
                </label>
            </div>
            <div>
                <label>
                    Language:
                    <select value={language} onChange={e => setLanguage(e.target.value)}>
                        <option value="pl">pl</option>
                        <option value="en">en</option>
                        <option value="other">other</option>
                    </select>
                </label>
            </div>
            <div>
                <label>
                    Source:
                    <input type="text" value={source} onChange={e => setSource(e.target.value)}
                           style={{width: '50ch'}}/>
                </label>
            </div>

            {
                documentType === "youtube" &&
                <div>
                    <label>
                        Make AI summary:
                        <input type="checkbox" checked={makeAISummary}
                               onChange={e => setMakeAISummary(e.target.checked)}/>
                    </label>
                </div>
            }
            {
                (documentType === "youtube" || documentType === "movie") &&

                <div>Chapter List:
                    <textarea name="chapterList" rows={6} cols={80} value={chapterList}
                              onChange={e => setChapterList(e.target.value)}/>
                </div>
            }
            <div>Note:
                <textarea name="note" rows={6} cols={80} value={note}
                          onChange={e => setNote(e.target.value)}/>
            </div>
            <div>Text:
                <textarea name="text" rows={6} cols={80} value={text}
                          onChange={e => setText(e.target.value)}/>
            </div>
            <div>
                <button onClick={() => handleSaveWebsite()}>save</button>
            </div>
            {message && <p>{message}</p>}

        </header>
    </div>
  );
}

export default App;
