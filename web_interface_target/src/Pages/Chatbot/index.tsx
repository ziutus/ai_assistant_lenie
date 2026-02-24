import React, { useEffect } from "react";

//import images
import avatar03 from "assets/images/avatar/03.png";
import avatar04 from "assets/images/avatar/04.png";
import avatar_user from "assets/images/users/jozwiak_krzysztof_logged_in_36.jpeg";
import { Link } from "react-router-dom";
import RightSidebar from "./RightSidebar";
import useSidebarToggle from "Common/UseSideberToggleHooks";

const Chatbot = () => {
    const themeSidebarToggle = useSidebarToggle();
    useEffect(() => {
        document.body.classList.add("chatbot");

        return () => {
            document.body.classList.remove("chatbot");
        };
    }, []);

    useEffect(() => {
        const handleScroll = () => {
            const distanceFromBottom = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;

            const threshold = 200;
            const searchForm: any = document.querySelector('.chatbot .search-form');

            if (distanceFromBottom < threshold) {
                searchForm.classList.add('active');
            } else {
                searchForm.classList.remove('active');
            }
        };

        window.addEventListener('scroll', handleScroll);
        return () => {
            window.removeEventListener('scroll', handleScroll);
        };
    }, []);

    return (
        <>
            <div className={`main-center-content-m-left center-content search-sticky ${themeSidebarToggle ? "collapsed" : ""}`}>
                <div className="question_answer__wrapper__chatbot">
                    <div className="single__question__answer">
                        <div className="question_user">
                            <div className="left_user_info">
                                <img src={avatar_user} alt="avatar" />
                                <div className="question__user">what is AI?</div>
                            </div>
                            <div className="edit__icon openuptip">
                                <i className="fa-regular fa-pen-to-square"></i>
                            </div>
                        </div>
                        <div className="answer__area">
                            <div className="thumbnail">
                                <img src={avatar04} alt="avatar" />
                            </div>
                            <div className="answer_main__wrapper">
                                <h4 className="common__title">OpenAI - GPT-4o</h4>
                                <p className="disc">
                                    Artificial Intelligence (AI) is a field of computer science that focuses on creating systems capable of performing tasks that typically require human intelligence, such as understanding language, recognizing patterns, and making decisions. These systems leverage algorithms and data to learn from experience and improve their performance over time.
                                </p>
                            </div>
                        </div>

                        <div className="share-reaction-area">
                            <ul>
                                <li><Link to="#" className="openuptip"><i className="fa-regular fa-bookmark"></i></Link></li>
                                <li><Link to="#" className="openuptip" ><i className="fa-light fa-thumbs-up"></i></Link></li>
                                <li><Link to="#" className="openuptip"><i className="fa-regular fa-thumbs-down"></i></Link></li>
                            </ul>
                        </div>
                    </div>
                    <div className="single__question__answer">
                        <div className="question_user">
                            <div className="left_user_info">
                                <img src={avatar_user} alt="avatar" />
                                <div className="question__user">Co to jest AI?</div>
                            </div>
                            <div className="edit__icon openuptip" >
                                <i className="fa-regular fa-pen-to-square"></i>
                            </div>
                        </div>
                        <div className="answer__area">
                            <div className="thumbnail">
                                <img src={avatar04} alt="avatar" />
                            </div>
                            <div className="answer_main__wrapper">
                                <h4 className="common__title">OpenAI - GPT-4o</h4>
                                <p className="disc">
                                    Sztuczna Inteligencja (AI) to dziedzina informatyki, która koncentruje się na tworzeniu systemów zdolnych do wykonywania zadań, które zazwyczaj wymagają ludzkiej inteligencji, takich jak rozumienie języka, rozpoznawanie wzorców i podejmowanie decyzji. Systemy te wykorzystują algorytmy i dane, aby uczyć się na podstawie doświadczeń i z czasem poprawiać swoją wydajność.
                                </p>
                            </div>
                        </div>

                        <div className="share-reaction-area">
                            <ul>
                                <li><Link to="#" className="openuptip"><i className="fa-regular fa-bookmark"></i></Link></li>
                                <li><Link to="#" className="openuptip"><i className="fa-light fa-thumbs-up"></i></Link></li>
                                <li><Link to="#" className="openuptip"><i className="fa-regular fa-thumbs-down"></i></Link></li>
                            </ul>
                        </div>
                    </div>
                    <div className="single__question__answer">
                        <div className="question_user">
                            <div className="left_user_info">
                                <img src={avatar_user} alt="avatar" />
                                <div className="question__user">Co to jest AI?</div>
                            </div>
                            <div className="edit__icon openuptip">
                                <i className="fa-regular fa-pen-to-square"></i>
                            </div>
                        </div>
                        <div className="answer__area">
                            <div className="thumbnail">
                                <img src={avatar04} alt="avatar" />
                            </div>
                            <div className="answer_main__wrapper">
                                <h4 className="common__title">Amazon Bedrock - Titan Text G1 - Express</h4>
                                <p className="disc">
                                    AI to skrót od angielskiego Artificial Intelligence, czyli sztuczna inteligencja. Artificial Intelligence to dyscyplina nauki, która zajmuje się budowaniem inteligentnych systemów, które mogą rozwiązywać problemy, które są charakterystyczne dla inteligentnych istot.
                                </p>
                            </div>
                        </div>

                        <div className="share-reaction-area">
                            <ul>
                                <li><Link to="#" className="openuptip"><i className="fa-regular fa-bookmark"></i></Link></li>
                                <li><Link to="#" className="openuptip"><i className="fa-light fa-thumbs-up"></i></Link></li>
                                <li><Link to="#" className="openuptip" ><i className="fa-regular fa-thumbs-down"></i></Link></li>
                            </ul>
                        </div>
                    </div>
                </div>
                <form action="#" className="search-form">
                    <input type="text" placeholder="Message openup..." />
                    <button><i className="fa-regular fa-arrow-up"></i></button>
                </form>
                <div className="copyright-area-bottom">
                    <p> <Link to="#">Reactheme©</Link> 2024. All Rights Reserved.</p>
                </div>
            </div>

            <RightSidebar />
        </>
    );
};

export default Chatbot;
