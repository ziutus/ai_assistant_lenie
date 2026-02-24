import React from "react";
import { Link } from "react-router-dom";

//import images
import banner from "assets/images/banner/01.png";
import generator from "assets/images/generator/01.jpg";
import generator2 from "assets/images/generator/02.jpg";
import generator3 from "assets/images/generator/03.jpg";
import useSidebarToggle from "Common/UseSideberToggleHooks";

import { RootState } from "Slices/theme/store";
import {useSelector} from "react-redux";

const Home = () => {
    const themeSidebarToggle = useSidebarToggle();
    // userInfo.tsx
    const user = useSelector((state: RootState) => state.user);

    return (
        <>
            <div
                className={`main-center-content-m-left main-center-content-m-left ${themeSidebarToggle ? "collapsed" : ""}`}>
                <div className="banner-badge bg_image">
                    <div className="inner">
                        <h3 className="title">Generate New Ideas for Your Content</h3>
                        <p className="dsic">
                            Lenie AI is the place to create, publish and monetize content using the power of AI. Use the
                            IntellectAi AI Studio to create amazing generative images, music, and audio.
                        </p>
                        <Link to="#" className="rts-btn btn-blur">Try Now</Link>
                        <div className="inner-right-iamge">
                            <img src={banner} alt="banner"/>
                        </div>
                    </div>
                </div>
                <div className="search__generator mt--50">
                    <h4 className="title color-white-title-home">👋 Welcome back, {user.name_nice}!</h4>

                    <div className="tab-content mt--50" id="pills-tabContent">
                        <div className="row g-5">
                            <div className="col-xl-4 col-lg-6 col-md-6 col-sm-12 col-12">
                                <div className="single-image-generator">
                                    <Link to="image-generator" className="thumbnail">
                                        <img src={generator} alt="images"/>
                                    </Link>
                                    <div className="inner-content">
                                        <div className="left-content-area">
                                            <h5 className="title">Image Generator</h5>
                                            <p className="disc">
                                                Our text-to-image feature turns your words into beautiful AI visuals.
                                            </p>
                                        </div>
                                        <Link to="/image-generator" className="rts-btn btn-primary">Generate</Link>
                                    </div>
                                </div>
                            </div>
                            <div className="col-xl-4 col-lg-6 col-md-6 col-sm-12 col-12">
                                <div className="single-image-generator">
                                    <Link to="/chatbot" className="thumbnail">
                                        <img src={generator2} alt="images"/>
                                    </Link>
                                    <div className="inner-content">
                                        <div className="left-content-area">
                                            <h5 className="title">Content Generator</h5>
                                            <p className="disc">
                                                Our text-to-image feature turns your words into beautiful AI visuals.
                                            </p>
                                        </div>
                                        <Link to="/chatbot" className="rts-btn btn-primary">Generate</Link>
                                    </div>
                                </div>
                            </div>
                            <div className="col-xl-4 col-lg-6 col-md-6 col-sm-12 col-12">
                                <div className="single-image-generator">
                                    <Link to="/voicegenerator" className="thumbnail">
                                        <img src={generator3} alt="images"/>
                                    </Link>
                                    <div className="inner-content">
                                        <div className="left-content-area">
                                            <h5 className="title">Voice Generator</h5>
                                            <p className="disc">
                                                Our text-to-image feature turns your words into beautiful AI visuals.
                                            </p>
                                        </div>
                                        <Link to="/voicegenerator" className="rts-btn btn-primary">Generate</Link>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="copyright-area-bottom">
                    <p><Link to="#">Reactheme©</Link> 2024. All Rights Reserved.</p>
                </div>
            </div>
        </>
    );
};

export default Home;
