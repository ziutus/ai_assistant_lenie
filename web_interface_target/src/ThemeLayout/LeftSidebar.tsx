import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

//import images
import icons01 from "assets/images/icons/01.png";
import icons02 from "assets/images/icons/02.png";
import icons03 from "assets/images/icons/03.png";
import icons04 from "assets/images/icons/04.png";
import icons05 from "assets/images/icons/05.png";
import icons06 from "assets/images/icons/06.png";
import icons07 from "assets/images/icons/07.png";
import icons08 from "assets/images/icons/08.png";
import icons09 from "assets/images/icons/09.png";
import icons14 from "assets/images/icons/14.png";
import avatar02 from "assets/images/avatar/02.png";
import { Collapse } from "react-bootstrap";
import { useSelector } from "react-redux";
import { RootState } from "Slices/theme/store";
import avatar_user from "assets/images/users/jozwiak_krzysztof_logged_in.jpeg";

const LeftSidebar = () => {
    const location = useLocation();
    const themeSidebarToggle = useSelector((state: RootState) => state.theme.themeSidebarToggle);
    const [open, setOpen] = useState(false);
    const user = useSelector((state: RootState) => state.user);

    const handleSettingsClick = () => {
        setOpen(!open);
    };

    const handleFaqClick = () => {
        if (open) {
            setOpen(false);
        }
    };
    return (
        <>
            <div className={`left-side-bar ${themeSidebarToggle ? "collapsed" : ""}`}>
                <div className="overlay-mobile-area"></div>
                <div className="inner">
                    <div className="single-menu-wrapper">
                        <Link to="/" className={`single-menu openuptip ${location.pathname === "/" ? "active" : ""
                            }`}>
                            <div className="icon">
                                <img src={icons01} alt="icons" />
                            </div>
                            <p>Home</p>
                        </Link>
                        <Link to="/links-list" className={`single-menu openuptip ${location.pathname === "/links-list" ? "active" : ""
                        }`}>
                            <div className="icon">
                                <img src={icons01} alt="icons" />
                            </div>
                            <p>Links List</p>
                        </Link>
                        <Link to="/link" className={`single-menu openuptip ${location.pathname === "/link" ? "active" : ""
                        }`}>
                            <div className="icon">
                                <img src={icons01} alt="icons" />
                            </div>
                            <p>Link</p>
                        </Link>
                        <Link to="/community-feed"
                            className={`single-menu openuptip ${location.pathname === "/community-feed" ? "active" : ""
                                }`}
                        >
                            <div className="icon">
                                <img src={icons02} alt="icons" />
                            </div>
                            <p>Community Feed</p>
                        </Link>
                        <Link to="/community-details"
                            className={`single-menu openuptip ${location.pathname === "/community-details" ? "active" : ""
                                }`}>
                            <div className="icon">
                                <img src={icons02} alt="icons" />
                            </div>
                            <p>Community Details</p>
                        </Link>
                        <Link to="/manage-subscription" className={`single-menu openuptip ${location.pathname === "/manage-subscription" ? "active" : ""
                            }`}>
                            <div className="icon">
                                <img src={icons03} alt="icons" />
                            </div>
                            <p>Manage Subscription</p>
                        </Link>
                    </div>
                    <div className="single-menu-wrapper">
                        <Link to="/chatbot" className={`single-menu openuptip ${location.pathname === "/chatbot" ? "active" : ""
                            }`}>
                            <div className="icon">
                                <img src={icons04} alt="icons" />
                            </div>
                            <p>AI Chat Bot</p>
                        </Link>
                        <Link to="/image-generator" className={`single-menu openuptip ${location.pathname === "/image-generator" ? "active" : ""
                            }`}>
                            <div className="icon">
                                <img src={icons05} alt="icons" />
                            </div>
                            <p>Image Generator</p>
                        </Link>
                        <Link to="/voicegenerator" className={`single-menu openuptip ${location.pathname === "/voicegenerator" ? "active" : ""
                            }`}>
                            <div className="icon">
                                <img src={icons06} alt="icons" />
                            </div>
                            <p>Voice Generate</p>
                        </Link>
                    </div>
                    <div className="single-menu-wrapper">
                        <Link to="/register" className="single-menu">
                            <div className="icon">
                                <img src={icons07} alt="icons" />
                            </div>
                            <p>Register</p>
                        </Link>
                        <Link
                            onClick={handleSettingsClick}
                            aria-expanded={open}
                            className="collapse-btn collapsed single-menu" to="#" role="button">
                            <div className="icon">
                                <img src={icons08} alt="icons" />
                            </div>
                            <p>Settings</p>
                        </Link>
                        <Collapse in={open}>
                            <ul className="submenu rts-default-sidebar-list">
                                <li>
                                    <Link to="/faq" className={`${location.pathname === "/faq" ? "active" : ""}`} onClick={handleFaqClick}>
                                        <i className="fa-sharp fa-regular fa-user"></i>
                                        <span>FAQ's</span>
                                    </Link>

                                </li>
                                <li>
                                    <Link to="/login">
                                        <i className="fa-sharp fa-regular fa-shopping-bag"></i>
                                        <span>log In</span>
                                    </Link>
                                </li>
                                <li>
                                    <Link to="/reset-password">
                                        <i className="fa-sharp fa-regular fa-users"></i>
                                        <span>Reset Password</span>
                                    </Link>
                                </li>
                            </ul>
                        </Collapse>
                        <Link to="/login" className="single-menu">
                            <div className="icon">
                                <img src={icons09} alt="icons" />
                            </div>
                            <p>Logout</p>
                        </Link>
                    </div>
                </div>
                <div className="bottom-user">
                    <div className="user-wrapper">
                        <img src={avatar_user} alt="avatar" />
                        <div className="info">
                            <h6 className="title">{user.name}</h6>
                            <Link to="#">{user.email}</Link>
                        </div>
                        <span>{user.access_package}</span>
                    </div>
                    <div className="pro-upgrade">
                        <button className="rts-btn btn-primary" data-bs-toggle="modal" data-bs-target="#exampleModal" data-bs-whatever="@mdo">
                            <img src={icons14} alt="icons" />
                            Upgrade To Pro
                        </button>
                    </div>
                </div>
            </div>
        </>
    );
};

export default LeftSidebar;
