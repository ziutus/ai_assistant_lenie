import React from "react";
import { Button, Container, Modal, Nav, Row, Tab, TabContent, TabPane, Tabs } from "react-bootstrap";
import { Link } from "react-router-dom";

interface ManageSubscriptionProps {
    isUpdateSubscription: boolean;
    toggleUpdateSubscription: () => void;
}

const ManageSubscription = ({
    isUpdateSubscription,
    toggleUpdateSubscription
}: ManageSubscriptionProps) => {
    return (
        <>
            <Modal show={isUpdateSubscription} onHide={toggleUpdateSubscription} id="exampleModal" aria-labelledby="exampleModalLabel" aria-hidden="true">
                <Modal.Header>
                    <button onClick={toggleUpdateSubscription} type="button" className="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </Modal.Header>
                <Modal.Body>
                    <div className="pricing-plane-area pb--50">
                        <Container>
                            <Row>
                                <div className="col-lgl-12">
                                    <div className="title-conter-area">
                                        <h2 className="title">
                                            Manage Subscription
                                        </h2>
                                        <span className="pre-title-bg">Want to get more out of Imagine AI? Subscribe to one of our professional plans.</span>
                                    </div>
                                </div>
                            </Row>

                            <Tab.Container defaultActiveKey="home">
                                <div className="tab-area-pricing-two mt--30">
                                    <Nav className="nav nav-tabs pricing-button-one two" id="myTab" role="tablist">
                                        <Nav.Item as="li">
                                            <Nav.Link as="button" eventKey="home" id="home-tab" type="button" role="tab" >Monthly Pricing</Nav.Link>
                                        </Nav.Item>
                                        <Nav.Item as="li">
                                            <Nav.Link as="button" eventKey="profile" id="profile-tab" type="button" role="tab">Annual Pricing</Nav.Link>
                                        </Nav.Item>
                                        <li className="save-badge">
                                            <span>SAVE 25%</span>
                                        </li>
                                    </Nav>
                                    <TabContent className="mt--20" id="myTabContent">
                                        <TabPane eventKey="home" id="home" role="tabpanel">
                                            <Row className="g-5 mt--10">
                                                <div className="col-lg-4 col-md-6 col-sm-12 col-12">
                                                    <div className="single-pricing-single-two">
                                                        <div className="head">
                                                            <span className="top">Basic</span>
                                                            <div className="date-use">
                                                                <h4 className="title">$Free</h4>
                                                                <span>/month</span>
                                                            </div>
                                                        </div>
                                                        <div className="body">
                                                            <p className="para">A premium pricing plan is a pricing <br /> structure that is designed.</p>

                                                            <div className="check-wrapper">
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>10,000 Monthly Word Limit</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>10+ Templates</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>All types of content</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>10+ Languages</p>
                                                                </div>
                                                            </div>
                                                            <Link to="#" className="pricing-btn">Get Started</Link>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="col-lg-4 col-md-6 col-sm-12 col-12">
                                                    <div className="single-pricing-single-two active">
                                                        <div className="head">
                                                            <span className="top">Diamond</span>
                                                            <div className="date-use">
                                                                <h4 className="title">$399</h4>
                                                                <span>/Month</span>
                                                            </div>
                                                        </div>
                                                        <div className="body">
                                                            <p className="para">A premium pricing plan is a pricing <br /> structure that is designed.</p>

                                                            <div className="check-wrapper">
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>60,000 Monthly Word Limit</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>60+ Templates</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>All types of content</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>60+ Languages</p>
                                                                </div>
                                                            </div>
                                                            <Link to="#" className="pricing-btn">Get Started</Link>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="col-lg-4 col-md-6 col-sm-12 col-12">
                                                    <div className="single-pricing-single-two">
                                                        <div className="head">
                                                            <span className="top">Premium</span>
                                                            <div className="date-use">
                                                                <h4 className="title">$199</h4>
                                                                <span>/Month</span>
                                                            </div>
                                                        </div>
                                                        <div className="body">
                                                            <p className="para">A premium pricing plan is a pricing <br /> structure that is designed.</p>

                                                            <div className="check-wrapper">
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>30,000 Monthly Word Limit</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>30+ Templates</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>All types of content</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>40+ Languages</p>
                                                                </div>
                                                            </div>
                                                            <Link to="#" className="pricing-btn">Get Started</Link>
                                                        </div>
                                                    </div>
                                                </div>
                                            </Row>
                                        </TabPane>
                                        <TabPane eventKey="profile" id="profile" role="tabpanel">
                                            <div className="row g-5 mt--10">
                                                <div className="col-lg-4 col-md-6 col-sm-12 col-12">
                                                    <div className="single-pricing-single-two">
                                                        <div className="head">
                                                            <span className="top">Basic</span>
                                                            <div className="date-use">
                                                                <h4 className="title">$Free</h4>
                                                                <span>/Year</span>
                                                            </div>
                                                        </div>
                                                        <div className="body">
                                                            <p className="para">A premium pricing plan is a pricing <br /> structure that is designed.</p>

                                                            <div className="check-wrapper">
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>10,000 Yearly Word Limit</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>10+ Templates</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>All types of content</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>10+ Languages</p>
                                                                </div>
                                                            </div>
                                                            <Link to="#" className="pricing-btn">Get Started</Link>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="col-lg-4 col-md-6 col-sm-12 col-12">
                                                    <div className="single-pricing-single-two active">
                                                        <div className="head">
                                                            <span className="top">Diamond</span>
                                                            <div className="date-use">
                                                                <h4 className="title">$399</h4>
                                                                <span>/Year</span>
                                                            </div>
                                                        </div>
                                                        <div className="body">
                                                            <p className="para">A premium pricing plan is a pricing <br /> structure that is designed.</p>

                                                            <div className="check-wrapper">
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>60,000 Yearly Word Limit</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>60+ Templates</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>All types of content</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>60+ Languages</p>
                                                                </div>
                                                            </div>
                                                            <Link to="#" className="pricing-btn">Get Started</Link>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="col-lg-4 col-md-6 col-sm-12 col-12">
                                                    <div className="single-pricing-single-two">
                                                        <div className="head">
                                                            <span className="top">Silver</span>
                                                            <div className="date-use">
                                                                <h4 className="title">$199</h4>
                                                                <span>/Year</span>
                                                            </div>
                                                        </div>
                                                        <div className="body">
                                                            <p className="para">A premium pricing plan is a pricing <br /> structure that is designed.</p>

                                                            <div className="check-wrapper">
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>30,000 Yearly Word Limit</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>30+ Templates</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>All types of content</p>
                                                                </div>
                                                                <div className="check-area">
                                                                    <i className="fa-solid fa-check"></i>
                                                                    <p>40+ Languages</p>
                                                                </div>
                                                            </div>
                                                            <Link to="#" className="pricing-btn">Get Started</Link>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </TabPane>
                                    </TabContent>
                                </div>
                            </Tab.Container>
                        </Container>
                    </div>
                </Modal.Body>
            </Modal>
        </>
    );
};

export default ManageSubscription;