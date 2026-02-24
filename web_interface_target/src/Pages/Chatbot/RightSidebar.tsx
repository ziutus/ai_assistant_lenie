import React, { useState } from "react";

//import images
import logo02 from "assets/images/logo/logo-02.png";
import icons04 from "assets/images/icons/04.png";
import icons05 from "assets/images/icons/05.svg";
import icons01 from "assets/images/icons/01.svg";

const RightSidebar = () => {

    const [isToggleRightSidebar, setIsToggleRightSidebar] = useState<boolean>(true);

    const toggleRightSidebar = () => {
        setIsToggleRightSidebar(!isToggleRightSidebar);
    }
    return (
        <>
            <div className={`right-side-bar-new-chat-option ${isToggleRightSidebar ? "" : "close-right"}`}>
                <div className="new-chat-option">
                    <img src={logo02} alt="logo" />
                    <img src={icons04} alt="icons" />
                </div>
                <div className="chat-history-wrapper">
                    <div className="chat-history-area-start">
                        <h6 className="title">Today</h6>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>ranking water is essential</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>These foods are calorie</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>If you're struggling to</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                    </div>
                    <div className="chat-history-area-start">
                        <h6 className="title">Yesterday</h6>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>ranking water is essential</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>These foods are calorie</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>If you're struggling to</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                    </div>
                    <div className="chat-history-area-start">
                        <h6 className="title">11/03/2024</h6>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>ranking water is essential</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>These foods are calorie</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>If you're struggling to</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                    </div>
                    <div className="chat-history-area-start">
                        <h6 className="title">28/04/2024</h6>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>ranking water is essential</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>These foods are calorie</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>If you're struggling to</p>
                            <img src={icons05} alt="icons" />
                        </div>
                        <div className="single-history">
                            <p>Online School Education</p>
                            <img src={icons05} alt="icons" />
                        </div>
                    </div>
                </div>
                <div
                    onClick={toggleRightSidebar}
                    className="right-side-open-clouse" id="collups-right">
                    <img src={icons01} alt="icons" />
                </div>
            </div>
        </>
    );
};

export default RightSidebar;