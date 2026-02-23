"use client";
import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import useAccordion from "@/components/hooks/useAccordion";
import Image from "next/image";
import Link from "next/link";

const Faq_1 = () => {
	const [activeIndex, handleAccordion] = useAccordion(0);

	return (
		<>
			<Header_01 />
			<main className="main-wrapper relative overflow-hidden">
				{/*...::: Breadcrumb Section Start :::... */}
				<section id="section-breadcrumb">
					{/* Section Spacer */}
					<div className="breadcrumb-wrapper">
						{/* Section Container */}
						<div className="global-container">
							<div className="breadcrumb-block">
								<h1 className="breadcrumb-title">FAQs</h1>
								<ul className="breadcrumb-nav">
									<li>
										<Link href="/">Home</Link>
									</li>
									<li>FAQs</li>
								</ul>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Breadcrumb Section End :::... */}
				{/*...::: FAQ Section Start :::... */}
				<section className="faq-section">
					{/* Section Spacer */}
					<div className="pb-20 xl:pb-[130px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 text-center lg:mb-16 xl:mb-20">
								<div className="mx-auto max-w-md lg:max-w-3xl xl:max-w-[950px]">
									<h2>Our experts are able to answer all your questions</h2>
								</div>
							</div>
							{/* Section Content Block */}
							{/* Accordion*/}
							<ul className="accordion flex flex-col gap-y-6">
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 0 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(0)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>What is Artificial Intelligence (AI)?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 1 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(1)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>What are the different types of AI?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 2 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(2)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>What are some practical applications of AI?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 3 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(3)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>
											What is the difference between AI and machine learning?
										</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 4 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(4)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>How can businesses AI for competitive advantage?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 5 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(5)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>Can AI replace humans in the workforce?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 6 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(6)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>Is AI safe?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
								{/* Accordion items */}
								<li
									className={`jos accordion-item is-2 rounded-[10px] border-[1px] border-[#EAEDF0] bg-white px-7 py-[30px] ${
										activeIndex === 7 ? "active" : ""
									}`}
									data-jos_delay="0.1"
									onClick={() => handleAccordion(7)}
								>
									<div className="accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[0.5px] lg:text-[28px]">
										<h5>What is the future of AI?</h5>
										<div className="accordion-icon">
											<Image
												src="/assets/img_placeholder/plus.svg"
												width={24}
												height={24}
												alt="plus"
											/>
										</div>
									</div>
									<div className="accordion-content text-[#2C2C2C]">
										<p>
											AI refers to the simulation of human intelligence in
											machines, enabling them to perform tasks that typically
											require human intelligence, such as learning, reasoning,
											problem-solving, and decision-making.
										</p>
									</div>
								</li>
								{/* Accordion items */}
							</ul>
							{/* Accordion*/}
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: FAQ Section End :::... */}
				{/*...::: About Contact Section Start :::... */}
				<section id="about-conact">
					{/* Section Spacer */}
					<div className="bg-black pb-40 pt-20 xl:pb-[200px] xl:pt-[130px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="grid grid-cols-1 items-center gap-14 md:grid-cols-[minmax(0,_1fr)_1.4fr]">
								{/* Content Left Block */}
								<div
									className="jos order-2 overflow-hidden rounded-[20px] md:order-1"
									data-jos_animation="fade-left"
								>
									<Image
										src="/assets/img_placeholder/th-1/about-contact-img.jpg"
										alt="about-contact-img"
										width={526}
										height={550}
										className="h-auto w-full"
									/>
								</div>
								{/* Content Left Block */}
								{/* Content Right Block */}
								<div
									className="jos order-1 md:order-2"
									data-jos_animation="fade-down"
								>
									&gt;
									{/* Section Content Block */}
									<div className="mb-8 max-w-sm md:max-w-max lg:mb-16 xl:mb-6">
										<h2 className="text-white">
											We always want to connect our clients
										</h2>
									</div>
									{/* Section Content Block */}
									<div className="text-left text-lg leading-[1.4] text-white lg:text-[21px]">
										<p className="mb-7 last:mb-0">
											AI accessible and beneficial for organizations, and we
											look forward to partnering with businesses to achieve
											their AI goals.
										</p>
									</div>
									<ul className="mt-10 flex flex-col gap-6 font-dmSans text-[30px] tracking-[1.33] lg:mt-14 lg:gap-y-3 xl:mt-[70px]">
										<li className="flex flex-col gap-x-2 leading-tight text-colorOrangyRed lg:flex-row lg:leading-normal">
											Website:
											<Link
												rel="noopener noreferrer"
												href="https://www.example.com"
												className="text-white hover:text-colorOrangyRed"
											>
												www.example.com
											</Link>
										</li>
										<li className="flex flex-col gap-x-2 leading-tight text-colorOrangyRed lg:flex-row lg:leading-normal">
											Email:
											<Link
												href="mailto:yourmail@mail.com"
												className="text-white hover:text-colorOrangyRed"
											>
												yourmail@mail.com
											</Link>
										</li>
										<li className="flex flex-col gap-x-2 leading-tight text-colorOrangyRed lg:flex-row lg:leading-normal">
											Phone:
											<Link
												href="tel:+1234567890"
												className="text-white hover:text-colorOrangyRed"
											>
												(123) 456-7890
											</Link>
										</li>
									</ul>
								</div>
								{/* Content Right Block */}
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: About Contact Section End :::... */}
			</main>
			<Footer_01/>
		</>
	);
};

export default Faq_1;
