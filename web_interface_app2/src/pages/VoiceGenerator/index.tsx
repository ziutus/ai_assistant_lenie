import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import RightSidebar from "./RightSidebar";

//import images
import icon06 from "assets/images/icons/06.svg";
import useSidebarToggle from "Common/UseSideberToggleHooks";

const VoiceGenerator = () => {
    const themeSidebarToggle = useSidebarToggle();
    useEffect(() => {
        document.body.classList.add("chatbot");

        return () => {
            document.body.classList.remove("chatbot");
        };
    }, []);

    useEffect(() => {
        const handleScroll = () => {
            const distanceFromBottom = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;

            const threshold = 200;
            const searchForm: any = document.querySelector('.chatbot .search-form');

            if (distanceFromBottom < threshold) {
                searchForm.classList.add('active');
            } else {
                searchForm.classList.remove('active');
            }
        };

        window.addEventListener('scroll', handleScroll);
        return () => {
            window.removeEventListener('scroll', handleScroll);
        };
    }, []);

    return (
        <>
            <div className={`main-center-content-m-left center-content search-sticky ${themeSidebarToggle ? "collapsed" : ""}`}>
                <div className="audio-main-generator-start">
                    <form action="#">
                        <div className="ask-for-audio">
                            <textarea placeholder="Here write text" required></textarea>
                            <i className="fa-light fa-pen-to-square"></i>
                            <div className="button-wrapper-generator">
                                <button className="rts-btn btn-primary">Generate
                                    <img src={icon06} alt="icons" />
                                </button>
                                <button className="mp3 rts-btn btn-border">
                                    MP3
                                    <i className="fa-sharp fa-light fa-chevron-down"></i>
                                </button>
                            </div>
                        </div>
                    </form>
                </div>

                <div className="audio-main-wrapper-top-bottom mb--60">
                    <div className="audio-main-wrapper">
                        <div className="audio-player">
                            <div className="timeline">
                                <div className="progress"></div>
                            </div>
                            <div className="controls">
                                <div className="play-container">
                                    <div className="toggle-play play">
                                    </div>
                                </div>
                                <div className="time">
                                    <div className="current">0:00</div>
                                    <div className="length"></div>
                                </div>
                                <div className="volume-container">
                                    <div className="volume-button">
                                        <div className="volume icono-volumeMedium"></div>
                                    </div>

                                    <div className="volume-slider">
                                        <div className="volume-percentage"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <button className="rts-btn btn-primary mt--30">Downloaded
                        <i className="fa-light fa-download ms-2"></i>
                    </button>
                </div>
                <div className="audio-main-generator-start">
                    <form action="#">
                        <div className="ask-for-audio">
                            <textarea placeholder="Here write text" required></textarea>
                            <i className="fa-light fa-pen-to-square"></i>
                            <div className="button-wrapper-generator">
                                <button className="rts-btn btn-primary">Generate
                                    <img src={icon06} alt="icons" />
                                </button>
                                <button className="mp3 rts-btn btn-border">
                                    MP3
                                    <i className="fa-sharp fa-light fa-chevron-down"></i>
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
                <div className="audio-main-wrapper-top-bottom mb--60">
                    <div className="audio-main-wrapper">
                        <div className="audio-players">
                            <div className="timeline">
                                <div className="progress"></div>
                            </div>
                            <div className="controls">
                                <div className="play-container">
                                    <div className="toggle-play play">
                                    </div>
                                </div>
                                <div className="time">
                                    <div className="current">0:00</div>
                                    <div className="length"></div>
                                </div>
                                <div className="volume-container">
                                    <div className="volume-button">
                                        <div className="volume icono-volumeMedium"></div>
                                    </div>

                                    <div className="volume-slider">
                                        <div className="volume-percentage"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <button className="rts-btn btn-primary mt--30">Downloaded
                        <i className="fa-light fa-download ms-2"></i>
                    </button>
                </div>
                <div className="audio-main-generator-start">
                    <form action="#">
                        <div className="ask-for-audio">
                            <textarea placeholder="Here write text" required></textarea>
                            <i className="fa-light fa-pen-to-square"></i>
                            <div className="button-wrapper-generator">
                                <button className="rts-btn btn-primary">Generate
                                    <img src={icon06} alt="icons" />
                                </button>
                                <button className="mp3 rts-btn btn-border">
                                    MP3
                                    <i className="fa-sharp fa-light fa-chevron-down"></i>
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
                <div className="audio-main-wrapper-top-bottom mb--120">
                    <div className="audio-main-wrapper">
                        <div className="audio-playerer">
                            <div className="timeline">
                                <div className="progress"></div>
                            </div>
                            <div className="controls">
                                <div className="play-container">
                                    <div className="toggle-play play">
                                    </div>
                                </div>
                                <div className="time">
                                    <div className="current">0:00</div>
                                    <div className="length"></div>
                                </div>
                                <div className="volume-container">
                                    <div className="volume-button">
                                        <div className="volume icono-volumeMedium"></div>
                                    </div>

                                    <div className="volume-slider">
                                        <div className="volume-percentage"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <button className="rts-btn btn-primary mt--30">Downloaded
                        <i className="fa-light fa-download ms-2"></i>
                    </button>
                </div>
                <form action="#" className="search-form">
                    <input type="text" placeholder="Message openup..." />
                    <button><i className="fa-regular fa-arrow-up"></i></button>
                </form>
                <div className="copyright-area-bottom">
                    <p> <Link to="#">Reactheme©</Link> 2024. All Rights Reserved.</p>
                </div>

            </div>

            <RightSidebar />
        </>
    );
};

export default VoiceGenerator;