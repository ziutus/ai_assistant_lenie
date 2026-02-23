import React, { useState } from "react";
import { Link } from "react-router-dom";

const RightSidebar = () => {

    const [isFirefly1, setIsFirefly1] = useState(false);
    const [isFirefly2, setIsFirefly2] = useState(false);
    const [isFirefly3, setIsFirefly3] = useState(false);
    const [isFirefly4, setIsFirefly4] = useState(false);

    return (
        <>
            <div className="right-side-bar-new-chat-option">


                <div className="image-generatore-right-sidebar-content">
                    <div className={`nice-select-wrap ${isFirefly1 ? "down" : ""}`}>
                        <Link
                            onClick={() => {
                                setIsFirefly1(!isFirefly1);
                            }}
                            to="#" className="drop">Firefly Image 1</Link>
                        <ul id="sort" style={{ display: isFirefly1 ? "block" : "none" }}>
                            <li><a href="#" id="asc">Name: Ascending</a></li><li><a href="#" id="desc">Name: Descending</a></li>
                            <li><a href="#" id="pop">Popularity</a></li>
                            <li><a href="#" id="low">Price: Low to High</a></li>
                            <li><a href="#" id="high">Price: High to Low</a></li>
                        </ul>
                    </div>
                    <div className="image-diamention single-diamention border-top mt--30 pt--30">
                        <h6 className="title">Image Diamention</h6>
                        <div className={`nice-select-wrap ${isFirefly2 ? "down" : ""}`}>
                            <Link
                                onClick={() => {
                                    setIsFirefly2(!isFirefly2);
                                }}
                                to="#" className="drop">1024x 1024</Link>
                            <ul id="sort" style={{ display: isFirefly2 ? "block" : "none" }}>
                                <li><a href="#" id="asc">Name: Ascending</a></li><li><a href="#" id="desc">Name: Descending</a></li>
                                <li><a href="#" id="pop">Popularity</a></li>
                                <li><a href="#" id="low">Price: Low to High</a></li>
                                <li><a href="#" id="high">Price: High to Low</a></li>
                            </ul>
                        </div>
                    </div>
                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Aspect ratio</h6>
                        <div className={`nice-select-wrap ${isFirefly3 ? "down" : ""}`}>
                            <Link
                                onClick={() => {
                                    setIsFirefly3(!isFirefly3);
                                }}
                                to="#" className="drop">Square (1:1)</Link>
                            <ul id="sort" style={{ display: isFirefly3 ? "block" : "none" }}>
                                <li><a href="#" id="desc">Square (1:3)</a></li>
                                <li><a href="#" id="pop">Square (1:4)</a></li>
                                <li><a href="#" id="low">Square (1:6)</a></li>
                                <li><a href="#" id="high">Square (1:9)</a></li>
                                <li><a href="#" id="high">Square (1:4)</a></li>
                            </ul>
                        </div>
                    </div>
                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Prompt Guidence</h6>
                        <div className="range-main-wrapper">
                            <div className="container1">
                                <input className="range" type="range" min="0" max="16" defaultValue="16" step="1" />
                                <output id="rangevalue1"></output>
                            </div>

                            <p className="disc mt--20">
                                Higher values will make your image closer to your prompt.
                            </p>
                        </div>

                    </div>

                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Quality & Details</h6>
                        <div className={`nice-select-wrap ${isFirefly4 ? "down" : ""}`}>
                            <Link
                                onClick={() => {
                                    setIsFirefly4(!isFirefly4);
                                }}
                                to="#" className="drop">High</Link>
                            <ul id="sort" style={{ display: isFirefly4 ? "block" : "none" }}>
                                <li><a href="#" id="desc">Medium</a></li>
                                <li><a href="#" id="pop">Low</a></li>
                                <li><a href="#" id="low">Small</a></li>
                                <li><a href="#" id="high">Extra Small</a></li>
                                <li><a href="#" id="high">Large</a></li>
                            </ul>
                        </div>
                        <p className="disc mt--20">
                            Higher quality will result in more steps, but will take longer.
                        </p>
                    </div>
                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Number Of Image</h6>

                        <div className="number-image-wrapper">
                            <span className="single-number">
                                1
                            </span>
                            <span className="single-number">
                                2
                            </span>
                            <span className="single-number">
                                3
                            </span>
                            <span className="single-number">
                                4
                            </span>
                        </div>
                    </div>
                </div>

            </div>
        </>
    );
};

export default RightSidebar;