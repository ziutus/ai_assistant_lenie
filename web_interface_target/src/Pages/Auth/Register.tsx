import React, { useEffect } from "react";
import { Col, Container, Row } from "react-bootstrap";

const Register = () => {

    useEffect(() => {
        document.body.classList.add("register");

        return () => {
            document.body.classList.remove("register");
        };
    }, []);
    
    return (
        <>
            <div className="dash-board-main-wrapper">
                <div className="main-center-content-m-left center-content">
                    <div className="rts-register-area">
                        <Container>
                            <Row>
                                <Col lg={12}>
                                    <div className="single-form-s-wrapper">
                                        <div className="head">
                                            <span>Start your Journey</span>
                                            <h5 className="title">Create an account</h5>
                                        </div>
                                        <div className="body">
                                            <form action="#">
                                                <div className="input-wrapper">
                                                    <input type="text" placeholder="Full Name" required />
                                                    <input type="email" placeholder="Enter your mail" />
                                                    <input type="password" placeholder="Enter your Password" />
                                                </div>
                                                <div className="check-wrapper">
                                                    <div className="form-check">
                                                        <input className="form-check-input" type="checkbox" value="" id="flexCheckDefault" />
                                                        <label className="form-check-label" htmlFor="flexCheckDefault">
                                                            I agree to privacy policy &amp; terms
                                                        </label>
                                                    </div>
                                                </div>
                                                <button className="rts-btn btn-primary">Create Account</button>
                                                <p>If you have an account? <a className="ml--5" href="login.html">Sign in</a></p>
                                            </form>
                                        </div>
                                        <div className="other-separator">
                                            <span>or</span>
                                        </div>
                                        <div className="sign-in-otherway">

                                            <div className="single">
                                                <div className="icon">
                                                    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                        <path d="M3.98918 10.878L3.36263 13.217L1.07258 13.2654C0.388195 11.996 0 10.5437 0 9.00034C0 7.50793 0.362953 6.10055 1.00631 4.86133H1.0068L3.04559 5.23511L3.9387 7.26166C3.75177 7.80661 3.64989 8.39161 3.64989 9.00034C3.64996 9.661 3.76963 10.294 3.98918 10.878Z" fill="#FBBB00"></path>
                                                        <path d="M17.8422 7.31836C17.9455 7.86279 17.9994 8.42504 17.9994 8.99967C17.9994 9.64402 17.9317 10.2725 17.8026 10.8788C17.3645 12.9419 16.2197 14.7434 14.6338 16.0182L14.6333 16.0177L12.0654 15.8867L11.7019 13.6179C12.7542 13.0007 13.5766 12.035 14.0098 10.8788H9.19727V7.31836H17.8422Z" fill="#518EF8"></path>
                                                        <path d="M14.6336 16.0173L14.6341 16.0178C13.0917 17.2575 11.1325 17.9993 8.99968 17.9993C5.57227 17.9993 2.59239 16.0836 1.07227 13.2644L3.98886 10.877C4.74891 12.9054 6.70567 14.3494 8.99968 14.3494C9.98571 14.3494 10.9095 14.0828 11.7021 13.6175L14.6336 16.0173Z" fill="#28B446"></path>
                                                        <path d="M14.7442 2.07197L11.8286 4.45894C11.0082 3.94615 10.0385 3.64992 8.99955 3.64992C6.65361 3.64992 4.66025 5.16013 3.93828 7.26131L1.00635 4.86098H1.00586C2.50373 1.97307 5.52119 0 8.99955 0C11.1833 0 13.1855 0.777867 14.7442 2.07197Z" fill="#F14336"></path>
                                                    </svg>
                                                </div>
                                                <p>Continue with Google</p>
                                            </div>


                                            <div className="single">
                                                <div className="icon">
                                                    <svg width="15" height="19" viewBox="0 0 15 19" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                        <path d="M10.9133 0H11.0427C11.1465 1.2826 10.6569 2.24096 10.062 2.93497C9.47815 3.62419 8.67872 4.29264 7.38574 4.19122C7.29949 2.92698 7.78985 2.0397 8.38403 1.34729C8.93508 0.701997 9.94535 0.127781 10.9133 0ZM14.8274 13.3499V13.3859C14.464 14.4864 13.9457 15.4296 13.3132 16.3048C12.7358 17.0995 12.0282 18.1689 10.7647 18.1689C9.67302 18.1689 8.94786 17.4669 7.82898 17.4477C6.64541 17.4285 5.99452 18.0347 4.91238 18.1872H4.54341C3.74877 18.0722 3.10747 17.4429 2.64027 16.8759C1.26264 15.2003 0.19806 13.0361 0 10.2664V9.4526C0.0838563 7.47039 1.04701 5.85876 2.32721 5.0777C3.00285 4.66241 3.93166 4.30861 4.96589 4.46674C5.40913 4.53543 5.86195 4.68717 6.25887 4.83731C6.63503 4.98186 7.10542 5.23822 7.55106 5.22464C7.85294 5.21586 8.15322 5.05853 8.4575 4.94752C9.34877 4.62567 10.2225 4.2567 11.3741 4.43001C12.7581 4.63925 13.7404 5.25419 14.3474 6.20297C13.1766 6.94809 12.251 8.07096 12.4091 9.98848C12.5497 11.7303 13.5624 12.7493 14.8274 13.3499Z" fill="black"></path>
                                                    </svg>
                                                </div>
                                                <p>Continue with Google</p>
                                            </div>

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

export default Register;