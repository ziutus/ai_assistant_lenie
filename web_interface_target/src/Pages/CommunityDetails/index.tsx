import React from "react";
import { Col, Container, Row } from "react-bootstrap";

//import images
import blog11 from "assets/images/blog/11.png";
import blog10 from "assets/images/blog/10.jpg";
import blog12 from "assets/images/blog/12.jpg";

const CommunityDetails = () => {
    return (
        <>
            <div className="blog-details-right-wrapper">
                <div className="rts-blog-details-area-top bg-smooth">
                    <Container>
                        <Row>
                            <Col lg={12}>
                                <Row className="top-blog-details-start align-items-center">
                                    <Col lg={6} md={12} sm={12} xs={12} className="mb--30">
                                        <div className="title-area">
                                            <h2 className="title">
                                                Five Things You Need to Know
                                                about Writing Articles
                                            </h2>
                                        </div>
                                    </Col>
                                    <Col lg={6} md={12} sm={12} xs={12}>
                                        <div className="authore-bd-area">
                                            <div className="main">
                                                <img src={blog11} alt="blog" />
                                                <div className="info">
                                                    <span className="deg">Author</span>
                                                    <span className="name">samuel</span>
                                                </div>
                                            </div>
                                            <div className="sub-area">
                                                <p>Category</p>
                                                <span className="deg">Blog Content</span>
                                            </div>
                                            <div className="sub-area">
                                                <p>Purplish</p>
                                                <span className="deg">15 may, 2023</span>
                                            </div>
                                        </div>
                                    </Col>
                                    <div className="col-lg-12 mt--30">
                                        <div className="main-image-big">
                                            <img src={blog10} alt="blog-imaeg" />
                                        </div>
                                    </div>
                                </Row>

                            </Col>
                        </Row>
                    </Container>
                </div>
                <div className="blog-detail-inenr-area pt--45 rts-section-gapBottom plr_sm--5 bg-smooth">
                    <div className="container-bd">
                        <Row>
                            <Col lg={12}>
                                <div className="para-area-wrapper">
                                    <p className="disc">
                                        As more consumers choose the internet and social media to interact with the brands they love, the need to be active on the social media with content has increased for businesses. And every platform demands a different type of content to be you successful. For example, Reels are the way to grow on Instagram for a lifestyle brand.
                                    </p>
                                    <p className="disc">
                                        daunting to create so much content manually. Whether you are a content creator, a marketer, or an entrepreneur, the content creation tools discussed in this blog post will help you nail the execution of your content marketing strategy.
                                    </p>
                                    <h4 className="title">10 Content creation tools to boost your productivity and make you more efficient</h4>
                                    <p className="disc">
                                        Deciding on the right content topics that bring results is not that easy. If you are still relying only on Google auto-populated prompts then your efforts are going to be half-baked. <br /> <br />

                                        Content research tools provide insights into what topics are trending in your industry, what your target audience is searching for, and how to optimize content for search engines. These tools will help you get results for your efforts.
                                        Here are the best content research tools to help you should know about.
                                    </p>
                                    <img className="mb--30" src={blog12} alt="dsds" />
                                    <h4 className="title">#1. ChatSonic - Like ChatGPT</h4>
                                    <p className="disc">
                                        There is no better tool than Chatsonic - Like ChatGPT with superpowers for content research. ChatGPT is a conversational AI technology that can understand, respond to, and generate text-based outputs. Chatsonic is the best alternative to ChatGPT as it overcomes the limitations of ChatGPT. You can speed up your content research by giving voice commands instead of typing, which is not possible on ChatGPT. The best part is the response speed is 2-3x faster than Google.
                                    </p>
                                    <div className="quote-area-bd">
                                        <div className="inner">
                                            <div className="icon">
                                                <svg width="21" height="31" viewBox="0 0 21 31" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                    <path d="M5.8125 27.4102V25.125H15.1875L15.1289 27.4102C15.1289 27.7031 15.0117 28.1719 14.8359 28.4062L13.8398 29.9297C13.5469 30.3984 12.8438 30.75 12.2578 30.75H8.68359C8.09766 30.75 7.39453 30.3984 7.10156 29.9297L6.10547 28.4062C5.87109 28.1133 5.8125 27.7617 5.8125 27.4102ZM10.5 0.75C16.1836 0.808594 20.8125 5.37891 20.8125 11.0625C20.8125 13.6992 19.8164 16.043 18.2344 17.8008C17.2383 18.9141 15.7734 21.2578 15.1875 23.1914C15.1875 23.1914 15.1875 23.1914 15.1875 23.25H5.75391C5.75391 23.1914 5.75391 23.1914 5.75391 23.1914C5.16797 21.2578 3.70312 18.9141 2.70703 17.8008C1.125 15.9844 0.1875 13.6406 0.1875 11.0625C0.1875 5.61328 4.52344 0.808594 10.5 0.75ZM16.125 16.043C17.2969 14.6367 18 12.8789 18 11.0625C18 6.96094 14.6016 3.5625 10.4414 3.5625C5.8125 3.62109 3 7.42969 3 11.0625C3 12.8789 3.64453 14.6367 4.81641 16.043C5.75391 17.0391 6.86719 18.7383 7.6875 20.4375H13.2539C14.0742 18.7383 15.1875 17.0391 16.125 16.043ZM9.5625 5.4375C10.0312 5.4375 10.5 5.90625 10.5 6.43359C10.5 6.90234 10.0312 7.3125 9.5625 7.3125C7.98047 7.3125 6.75 8.60156 6.75 10.125C6.75 10.6523 6.28125 11.0625 5.8125 11.0625C5.28516 11.0625 4.875 10.6523 4.875 10.125C4.875 7.54688 6.92578 5.4375 9.5625 5.4375Z" fill="#563EED"></path>
                                                </svg>
                                            </div>
                                            <h5 className="title">
                                                ChatSonic is a more advanced AI chatbot than ChatGPT <br />
                                                <span>due to its array of capabilities.</span>
                                            </h5>
                                        </div>
                                    </div>
                                    <h4 className="title">A robust tech stack of content creation tools makes you more efficient</h4>
                                    <p className="disc">
                                        AI content creation tools are game changers. These tools don’t only revolutionize the way content is created but also save you time from posting repetitive content. Looking at and going through so many tools can be quite overwhelming. The best thing to do is look for an all-in-one content creation tool.
                                    </p>
                                    <p className="disc">
                                        Use OpenUp 80+ powerful features like Instant article writer, paraphraser, website copy, and many more to fulfill every Ai content requirement you might have. Photosonic, a part of OpenUp can help you generate the perfect image to add visual appeal to your content. The best thing is you can use both OpenUp and Photosonic by just giving voice commands on Chatsonic.
                                        Boost your content creation with OpenUp today!
                                    </p>
                                </div>
                            </Col>
                        </Row>
                    </div>
                </div>
            </div>
        </>
    );
};

export default CommunityDetails;