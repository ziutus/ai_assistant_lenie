import React, { useEffect } from "react";
import { Col, Container, Row } from "react-bootstrap";
import { Link } from "react-router-dom";

const ResetPassword = () => {

    useEffect(() => {
        document.body.classList.add("register");

        return () => {
            document.body.classList.remove("register");
        };
    }, []);

    return (
        <>
            <div className="dash-board-main-wrapper pt--10">
                <div className="main-center-content-m-left center-content">
                    <div className="rts-register-area">
                        <Container>
                            <Row>
                                <Col lg={12}>
                                    <div className="single-form-s-wrapper reset text-start ptb--150 ptb_sm--50">
                                        <div className="head">
                                            <h5 className="title">Reset Your Password</h5>
                                            <p className="mb--20">Strong passwords include numbers, letters, and
                                                punctuation marks.</p>
                                        </div>
                                        <div className="body">
                                            <form action="#">
                                                <div className="input-wrapper">
                                                    <input type="email" placeholder="Enter your mail" required />
                                                </div>
                                                <div className="check-wrapper">
                                                    <div className="form-check">
                                                        <input className="form-check-input" type="checkbox" value="" id="flexCheckDefault" />
                                                        <label className="form-check-label" htmlFor="flexCheckDefault">
                                                            I agree to privacy policy &amp; terms
                                                        </label>
                                                    </div>
                                                </div>
                                                <button type="submit" className="rts-btn btn-primary">Send Reset Link</button>
                                                <p><Link to="/login"><i className="fa-solid fa-arrow-left"></i> Back to Login</Link></p>
                                            </form>
                                        </div>
                                    </div>
                                </Col>
                            </Row>
                        </Container>
                    </div>
                </div>
            </div>
        </>
    );
};

export default ResetPassword;