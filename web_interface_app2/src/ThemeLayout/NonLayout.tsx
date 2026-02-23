import React, { ReactNode } from "react";

interface NonLayout {
    children: ReactNode;
}
const NonLayout = ({ children }: NonLayout) => {
    return (
        <>
            {children}
        </>
    );
};

export default NonLayout;