import useSidebarToggle from "Common/UseSideberToggleHooks";
import React, { useEffect, useState } from "react";
import { Col, Container, Nav, Row, Tab, TabContainer } from "react-bootstrap";
import { Link } from "react-router-dom";

const ManageSubscription = () => {
    const [activeIndex, setActiveIndex] = useState(0);
    const themeSidebarToggle = useSidebarToggle();
    const handleToggle = (index: any) => {
        setActiveIndex(activeIndex === index ? null : index);
    };

    const accordionData = [
        {
            title: 'What is openup content writing tool?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'What languages does it supports?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'What is SEO writing AI and how do I use it?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'What languages does it supports?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'Does Openup To write long articles?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
    ];

    return (
        <>
            <div className={`main-center-content-m-left ${themeSidebarToggle ? "collapsed" : ""}`}>

                <div className="pricing-plane-area rts-section-gapBottom">
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

                        <TabContainer defaultActiveKey="home">
                            <div className="tab-area-pricing-two mt--30">
                                <Nav className="nav-tabs pricing-button-one two" id="myTab" role="tablist">
                                    <Nav.Item as="li" role="presentation">
                                        <Nav.Link as="button" eventKey="home" id="home-tab">Monthly Pricing</Nav.Link>
                                    </Nav.Item>
                                    <Nav.Item as="li" role="presentation">
                                        <Nav.Link as="button" eventKey="profile" id="profile-tab">Annual Pricing</Nav.Link>
                                    </Nav.Item>
                                    <li className="save-badge">
                                        <span>SAVE 25%</span>
                                    </li>
                                </Nav>
                                <Tab.Content className="mt--20" id="myTabContent">
                                    <Tab.Pane eventKey="home">
                                        <div className="row g-5 mt--10">
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
                                                        <a href="#" className="pricing-btn">Get Started</a>
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
                                                        <a href="#" className="pricing-btn">Get Started</a>
                                                    </div>
                                                </div>

                                            </div>
                                            <div className="col-lg-4 col-md-6 col-sm-12 col-12">

                                                <div className="single-pricing-single-two">
                                                    <div className="head">
                                                        <span className="top">Premium</span>
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
                                                        <a href="#" className="pricing-btn">Get Started</a>
                                                    </div>
                                                </div>

                                            </div>
                                        </div>
                                    </Tab.Pane>
                                    <Tab.Pane eventKey="profile">
                                        <div className="row g-5 mt--10">
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
                                                        <a href="#" className="pricing-btn">Get Started</a>
                                                    </div>
                                                </div>

                                            </div>
                                            <div className="col-lg-4 col-md-6 col-sm-12 col-12">

                                                <div className="single-pricing-single-two active">
                                                    <div className="head">
                                                        <span className="top">Diamond</span>
                                                        <div className="date-use">
                                                            <h4 className="title">$399</h4>
                                                            <span>/month</span>
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
                                                        <a href="#" className="pricing-btn">Get Started</a>
                                                    </div>
                                                </div>

                                            </div>
                                            <div className="col-lg-4 col-md-6 col-sm-12 col-12">

                                                <div className="single-pricing-single-two">
                                                    <div className="head">
                                                        <span className="top">Silver</span>
                                                        <div className="date-use">
                                                            <h4 className="title">$199</h4>
                                                            <span>/month</span>
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
                                                        <a href="#" className="pricing-btn">Get Started</a>
                                                    </div>
                                                </div>

                                            </div>
                                        </div>
                                    </Tab.Pane>
                                </Tab.Content>
                            </div>
                        </TabContainer>
                    </Container>
                </div>

                <div className="rts-faq-area rts-section-gapBottom bg_faq">
                    <div className="container">
                        <Row>
                            <Col lg={12}>
                                <div className="title-conter-area dashboard">
                                    <h2 className="title">
                                        Frequently Asked Questions
                                    </h2>
                                    <p className="disc">
                                        Can’t find the answer you’re looking for? Reach out to our customer support team
                                    </p>
                                </div>
                            </Col>
                        </Row>
                        <div className="row mt--60">
                            <Col lg={12}>
                                <div className="accordion-area-one">
                                    <div className="accordion" id="accordionExample">
                                        {accordionData.map((item, index) => (
                                            <div className="accordion-item" key={index}>
                                                <h2 className="accordion-header" id={`heading${index}`}>
                                                    <button
                                                        className={`accordion-button ${activeIndex === index ? '' : 'collapsed'}`}
                                                        type="button"
                                                        onClick={() => handleToggle(index)}
                                                        aria-expanded={activeIndex === index}
                                                        aria-controls={`collapse${index}`}
                                                    >
                                                        {item.title}
                                                    </button>
                                                </h2>
                                                <div
                                                    id={`collapse${index}`}
                                                    className={`accordion-collapse collapse ${activeIndex === index ? 'show' : ''}`}
                                                    aria-labelledby={`heading${index}`}
                                                    data-bs-parent="#accordionExample"
                                                >
                                                    <div className="accordion-body">
                                                        {item.content}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </Col>
                        </div>
                    </div>
                </div>

            </div>

            <div className="copyright-area-bottom">
                <p> <Link to="#">Reactheme©</Link> 2024. All Rights Reserved.</p>
            </div>
        </>
    );
};

export default ManageSubscription;