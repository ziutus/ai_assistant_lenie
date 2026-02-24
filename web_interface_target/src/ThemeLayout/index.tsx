import React, { ReactNode } from "react";
import TopBar from "./TopBar";
import LeftSidebar from "./LeftSidebar";

interface ThemeLayoutProps {
    children: ReactNode;
}
const ThemeLayout = ({ children }: ThemeLayoutProps) => {
    return (
        <>
            <TopBar />
            <div className="dash-board-main-wrapper">
                <LeftSidebar />
                {children}
            </div>
        </>
    );
};

export default ThemeLayout;