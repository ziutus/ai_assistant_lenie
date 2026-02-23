import React, { useState } from "react";
import { Col, Container, Row } from "react-bootstrap";

const Faq = () => {

    const [activeIndex, setActiveIndex] = useState(0);

    const handleToggle = (index: any) => {
        setActiveIndex(activeIndex === index ? null : index);
    };

    const accordionData = [
        {
            title: 'What is openup content writing tool?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'What languages does it support?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'What is SEO writing AI and how do I use it?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
        {
            title: 'Does Openup write long articles?',
            content: 'Once you know your audience, choose a topic that will resonate with them. Look for trending topics in your industry or address common questions or challenges your audience may be facing.'
        },
    ];
    return (
        <>
            <div className="main-center-content-m-left">

                <div className="rts-faq-area rts-section-gapBottom bg_faq">
                    <Container>
                        <Row>
                            <Col lg={12}>
                                <div className="title-conter-area dashboard">
                                    <h2 className="title">
                                        Questions About our OpenUp? <br />
                                        We have Answers!
                                    </h2>
                                    <p className="disc">
                                        please feel free to reach out to us. We are always happy to assist <br /> you and provide any additional information you may need.
                                    </p>
                                </div>
                            </Col>
                        </Row>
                        <Row className="mt--60">
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
                        </Row>
                    </Container>
                </div>

            </div>
        </>
    );
};

export default Faq;