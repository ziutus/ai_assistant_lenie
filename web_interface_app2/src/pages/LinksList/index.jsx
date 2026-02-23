import React from "react";
import { Link, NavLink } from "react-router-dom";

import useSidebarToggle from "Common/UseSideberToggleHooks";

import {useList} from "../../hooks/useList";

const LinksList = () => {
    const themeSidebarToggle = useSidebarToggle();
    const { isLoading, isError, data, message, handleGetList } = useList();
    // userInfo.tsx

    return (
        <>
            <div
                className={`main-center-content-m-left main-center-content-m-left ${themeSidebarToggle ? "collapsed" : ""}`}>
                {isLoading && (
                    <div style={{ marginBottom: "10px" }} className={"loader"}></div>
                )}
                <div className="search__generator mt--50">
                    <h4 className="title color-white-title-home"> Your list of links etc</h4>

                </div>
                {isError && (
                    <div>
                        <p className={"errorText"}>{message}</p>
                        <button
                            disabled={isLoading}
                            className={"button"}
                            type={"button"}
                            onClick={handleGetList}
                        >
                            Try again
                        </button>
                    </div>
                )}
                <ul>
                    {data &&
                        data.map((item) => (
                            <li
                                key={item.id}
                                className={"flexBox"}
                                style={{
                                    marginBottom: "7px",
                                    paddingBottom: "7px",
                                    borderBottom: "1px solid rgb(179, 179, 179)"
                                }}
                            >
                                {item.id}&nbsp;&nbsp;|&nbsp;&nbsp;
                                {item.title} &nbsp;
                                <a
                                    href={item.url}
                                    style={{ color: "rgba(0,122,255)" }}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    {(item.title && item.title.length > 10) ? item.url.substring(0, 50) + '...' : item.url}
                                </a>
                                <span style={{ margin: "0 0 0 auto", fontWeight: "500" }}>
                {item.document_type}
              </span>
                                <NavLink
                                    className={"button"}
                                    style={{ margin: "0 0 0 10px" }}
                                    onClick={() => {}}
                                    to={`/${item.document_type}/${item.id}`}
                                >
                                    Edit
                                </NavLink>
                                <button
                                    className={"button"}
                                    style={{ margin: "0 0 0 10px" }}
                                    onClick={() => {
                                        // Todo: Implement delete method
                                    }}
                                >
                                    Delete
                                </button>
                            </li>
                        ))}
                </ul>



                <div className="copyright-area-bottom">
                    <p><Link to="#">Reactheme©</Link> 2024. All Rights Reserved.</p>
                </div>
            </div>
        </>
    );
};

export default LinksList;
