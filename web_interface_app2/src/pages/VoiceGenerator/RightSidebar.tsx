import React, { useState } from "react";

const RightSidebar = () => {
    const [isLanguage, setIsLanguage] = useState(false);
    return (
        <>
            <div className="right-side-bar-new-chat-option">

                <div className="image-generatore-right-sidebar-content">

                    <div className="image-diamention single-diamention">
                        <h6 className="title">Language</h6>
                        <select className="nice-select" name="sort" multiple>
                            <option>Select Language</option>
                            <option value="asc">Bangla</option>
                            <option value="desc">English</option>
                            <option value="pop">Hindi</option>
                        </select>
                    </div>
                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Play Speed</h6>
                        <div className="range-main-wrapper">
                            <div className="container1">
                                <input className="range" type="range" min="0" max="10" value="10" step="1" />
                                <output id="rangevalue1">10</output>
                            </div>

                            <p className="disc mt--20">
                                Higher values will make your image closer to your prompt.
                            </p>
                        </div>

                    </div>

                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Quality & Details</h6>
                        <select className="nice-select" name="sort" multiple>
                            <option>High</option>
                            <option value="asc">Medium</option>
                            <option value="desc">Low</option>
                            <option value="pop">Small</option>
                            <option value="low">Extra Small</option>
                            <option value="high">Large</option>
                        </select>
                        <p className="disc mt--20">
                            Higher quality will result in more steps, but will take longer.
                        </p>
                    </div>
                    <div className="image-diamention single-diamention pt--30">
                        <h6 className="title">Format</h6>

                        <div className="number-image-wrapper">
                            <span className="single-number">
                                WAV
                            </span>
                            <span className="single-number">
                                Mp3
                            </span>
                            <span className="single-number">
                                AAC
                            </span>
                            <span className="single-number">
                                AIFF
                            </span>
                        </div>
                    </div>
                </div>

            </div>
        </>
    )
}

export default RightSidebar;