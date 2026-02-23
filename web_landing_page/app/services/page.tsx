"use client";
import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import useAccordion from "@/components/hooks/useAccordion";
import Image from "next/image";
import Link from "next/link";

function Services() {
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
								<h1 className="breadcrumb-title">Our Services</h1>
								<ul className="breadcrumb-nav">
									<li>
										<Link href="/">Home</Link>
									</li>
									<li>Our Services</li>
								</ul>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Breadcrumb Section End :::... */}
				{/*...::: Service Section Start :::... */}
				<section id="section-service">
					{/* Section Spacer */}
					<div className="pb-20 xl:pb-[150px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 text-center lg:mb-16 xl:mb-20">
								<div className="mx-auto max-w-md lg:max-w-xl xl:max-w-[950px]">
									<h2>We provide smart AI solutions for all tasks</h2>
								</div>
							</div>
							{/* Section Content Block */}
							{/* Service List */}
							<ul className="jos grid grid-cols-1 gap-[2px] overflow-hidden rounded-[10px] border-2 border-black bg-black sm:grid-cols-2 lg:grid-cols-4">
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-1.svg"
											alt="service-icon-black-1"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-1.svg"
											alt="service-icon-orange-1"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Resource Flexibility
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										This is an excellent option for people &amp; small
										businesses who are starting out.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-2.svg"
											alt="service-icon-black-2"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-2.svg"
											alt="service-icon-orange-1"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Managed Services
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										This is an excellent option for people &amp; small
										businesses who are starting out.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
									{/* Features Item */}
									{/* Features Item */}
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-3.svg"
											alt="service-icon-black-3"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-3.svg"
											alt="service-icon-orange-3"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Web-Based Access
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										This is an excellent option for people &amp; small
										businesses who are starting out.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-4.svg"
											alt="service-icon-black-4"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-4.svg"
											alt="service-icon-orange-4"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Resource Flexibility
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										This is an excellent option for people &amp; small
										businesses who are starting out.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-5.svg"
											alt="service-icon-black-5"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-5.svg"
											alt="service-icon-orange-5"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Anomaly Detection
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										AI SaaS can analyze IoT sensor data to detect predict
										equipment failures.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-6.svg"
											alt="service-icon-black-6"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-6.svg"
											alt="service-icon-orange-6"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Predictive Analytics
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										Solutions that use AI to predict future trends and outcomes,
										such as demand forecastin.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
									{/* Features Item */}
									{/* Features Item */}
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-7.svg"
											alt="service-icon-black-7"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-7.svg"
											alt="service-icon-orange-7"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Speech Recognition
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										Speech recognition services convert spoken language into
										text and accessibility.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
								</li>
								{/* Service Item */}
								{/* Service Item */}
								<li className="group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black">
									<div className="relative mb-9 h-[70px] w-[70px]">
										<Image
											src="/assets/img_placeholder/th-1/service-icon-black-8.svg"
											alt="service-icon-black-8"
											width={70}
											height={70}
										/>
										<Image
											src="/assets/img_placeholder/th-1/service-icon-orange-8.svg"
											alt="service-icon-orange-8"
											width={70}
											height={70}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</div>
									<h3 className="mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]">
										<Link
											href="/service-details"
											className="hover:text-colorOrangyRed"
										>
											Computer Vision
										</Link>
									</h3>
									<p className="mb-12 duration-300 group-hover:text-white">
										Computer vision services use AI to interpret and process
										visual information.
									</p>
									<Link
										href="/service-details"
										className="relative inline-block h-[30px] w-[30px] duration-300"
									>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-black.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
										/>
										<Image
											src="/assets/img_placeholder/th-1/arrow-right-orange.svg"
											alt="arrow-right-black"
											width={30}
											height={30}
											className="absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100"
										/>
									</Link>
								</li>
								{/* Service Item */}
							</ul>
							{/* Service List */}
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Service Section End :::... */}
				{/*...::: FAQ Section Start :::... */}
				<section className="faq-section">
					{/* Section Spacer */}
					<div className="pb-20 xl:pb-[150px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="grid grid-cols-1 gap-y-10 md:grid-cols-2">
								{/* FAQ Left Block */}
								<div
									className="jos flex flex-col"
									data-jos_animation="fade-right"
								>
									{/* Section Content Block */}
									<div className="mb-6">
										<div className="mx-auto md:mx-0 md:max-w-none">
											<h2>Freely ask us for more information</h2>
										</div>
									</div>
									{/* Section Content Block */}
									<div className="text-lg leading-[1.4] lg:text-[21px]">
										<p className="mb-7 last:mb-0">
											Our AI SaaS solutions can be quickly deployed, enabling
											users to start benefiting from AI capabilities without
											lengthy setup and development times in fast-paced
											industries.
										</p>
										<Link
											href="/faq-1"
											className="button mt-5 rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white"
										>
											Ask you questions
										</Link>
									</div>
								</div>
								{/* FAQ Left Block */}
								{/* FAQ Right Block */}
								<div
									className="jos md:ml-10 lg:ml-20 xl:ml-32"
									data-jos_animation="fade-left"
								>
									{/* Accordion*/}
									<ul className="accordion">
										{/* Accordion items */}
										<li
											className={`accordion-item border-b-[1px] border-[#DBD6CF] pb-6 pt-6 first:pt-0 last:border-b-0 last:pb-0 ${
												activeIndex == 0 && "active"
											}`}
										>
											<div
												onClick={() => handleAccordion(0)}
												className="accordion-header flex items-center justify-between font-dmSans text-xl font-bold leading-[1.2] -tracking-[0.5px] text-black lg:text-[28px]"
											>
												<p>How do I start AI SaaS?</p>
												<div className="accordion-icon">
													<Image
														src="/assets/img_placeholder/plus.svg"
														alt="plus"
														width={24}
														height={24}
													/>
												</div>
											</div>
											<div className="accordion-content text-[#2C2C2C]">
												<p>
													Go to the our official website and require users to
													create an account. You ll need to provide some basic
													information and agree to our terms and conditions.
												</p>
											</div>
										</li>
										{/* Accordion items */}
										{/* Accordion items */}
										<li
											className={`accordion-item border-b-[1px] border-[#DBD6CF] pb-6 pt-6 first:pt-0 last:border-b-0 last:pb-0 ${
												activeIndex == 1 && "active"
											}`}
										>
											<div
												onClick={() => handleAccordion(1)}
												className="accordion-header flex items-center justify-between font-dmSans text-xl font-bold leading-[1.2] -tracking-[0.5px] text-black lg:text-[28px]"
											>
												<p>Can I customize AI SaaS solutions?</p>
												<div className="accordion-icon">
													<Image
														src="/assets/img_placeholder/plus.svg"
														alt="plus"
														width={24}
														height={24}
													/>
												</div>
											</div>
											<div className="accordion-content text-[#2C2C2C]">
												<p>
													Go to the our official website and require users to
													create an account. You ll need to provide some basic
													information and agree to our terms and conditions.
												</p>
											</div>
										</li>
										{/* Accordion items */}
										{/* Accordion items */}
										<li
											className={`accordion-item border-b-[1px] border-[#DBD6CF] pb-6 pt-6 first:pt-0 last:border-b-0 last:pb-0 ${
												activeIndex == 2 && "active"
											}`}
										>
											<div
												onClick={() => handleAccordion(2)}
												className="accordion-header flex items-center justify-between font-dmSans text-xl font-bold leading-[1.2] -tracking-[0.5px] text-black lg:text-[28px]"
											>
												<p>How can AI benefit my business?</p>
												<div className="accordion-icon">
													<Image
														src="/assets/img_placeholder/plus.svg"
														alt="plus"
														width={24}
														height={24}
													/>
												</div>
											</div>
											<div className="accordion-content text-[#2C2C2C]">
												<p>
													Go to the our official website and require users to
													create an account. You ll need to provide some basic
													information and agree to our terms and conditions.
												</p>
											</div>
										</li>
									</ul>
									{/* Accordion*/}
								</div>
								{/* FAQ Right Block */}
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: FAQ Section End :::... */}
				{/*...::: Testimonial Section Start :::... */}
				<section className="testimonial-section">
					{/* Section Spacer */}
					<div className="bg-black pb-40 pt-20 xl:pb-[200px] xl:pt-[130px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 text-center lg:mb-16 xl:mb-20">
								<div className="mx-auto max-w-[300px] lg:max-w-[600px] xl:max-w-[680px]">
									<h2 className="text-white">
										Positive feedback from our users
									</h2>
								</div>
							</div>
							{/* Section Content Block */}
							{/* Testimonial List */}
							<div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
								{/* Testimonial Item */}
								<div
									className="jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white"
									data-jos_animation="fade-left"
									data-jos_delay="0.1"
								>
									<div className="block">
										<Image
											src="/assets/img_placeholder/th-1/rating.svg"
											alt="rating"
											width={146}
											height={25}
										/>
									</div>
									<p>
										“This AI SaaS tool has revolutionized the way we process and
										analyze data. This is a game-changer for our business.”
									</p>
									<div className="flex items-center gap-x-4">
										<div className="h-[60px] w-[60px] overflow-hidden rounded-full">
											<Image
												src="/assets/img_placeholder/th-1/testimonial-img-1.jpg"
												alt="testimonial-img"
												width={60}
												height={60}
												className="h-full w-full object-cover object-center"
											/>
										</div>
										<div className="flex flex-col gap-y-1">
											<span className="block text-lg font-semibold leading-[1.6]">
												Max Weber
											</span>
											<span className="block text-sm font-light leading-[1.4]">
												HR Manager
											</span>
										</div>
									</div>
								</div>
								{/* Testimonial Item */}
								{/* Testimonial Item */}
								<div
									className="jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white"
									data-jos_animation="fade-left"
									data-jos_delay="0.2"
								>
									<div className="block">
										<Image
											src="/assets/img_placeholder/th-1/rating.svg"
											alt="rating"
											width={146}
											height={25}
										/>
									</div>
									<p>
										It answers immediately, and we ve seen a significant
										reduction in response time. Our customers love it and so do
										we!
									</p>
									<div className="flex items-center gap-x-4">
										<div className="h-[60px] w-[60px] overflow-hidden rounded-full">
											<Image
												src="/assets/img_placeholder/th-1/testimonial-img-2.jpg"
												alt="testimonial-img"
												width={60}
												height={60}
												className="h-full w-full object-cover object-center"
											/>
										</div>
										<div className="flex flex-col gap-y-1">
											<span className="block text-lg font-semibold leading-[1.6]">
												Douglas Smith
											</span>
											<span className="block text-sm font-light leading-[1.4]">
												Businessman
											</span>
										</div>
									</div>
								</div>
								{/* Testimonial Item */}
								{/* Testimonial Item */}
								<div
									className="jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white"
									data-jos_animation="fade-left"
									data-jos_delay="0.3"
								>
									<div className="block">
										<Image
											src="/assets/img_placeholder/th-1/rating.svg"
											alt="rating"
											width={146}
											height={25}
										/>
									</div>
									<p>
										It is accurate, fast and supports multiple languages
										support. It is a must for any international business
										success.
									</p>
									<div className="flex items-center gap-x-4">
										<div className="h-[60px] w-[60px] overflow-hidden rounded-full">
											<Image
												src="/assets/img_placeholder/th-1/testimonial-img-3.jpg"
												alt="testimonial-img"
												width={60}
												height={60}
												className="h-full w-full object-cover object-center"
											/>
										</div>
										<div className="flex flex-col gap-y-1">
											<span className="block text-lg font-semibold leading-[1.6]">
												Abraham Maslo
											</span>
											<span className="block text-sm font-light leading-[1.4]">
												Founder @ Marketing Company
											</span>
										</div>
									</div>
								</div>
								{/* Testimonial Item */}
								{/* Testimonial Item */}
								<div
									className="jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white"
									data-jos_animation="fade-right"
									data-jos_delay="0.1"
								>
									<div className="block">
										<Image
											src="/assets/img_placeholder/th-1/rating.svg"
											alt="rating"
											width={146}
											height={25}
										/>
									</div>
									<p>
										Security is a top concern for us, and AI SaaS takes it
										seriously. Its a reassuring layer of protection for our
										organization.
									</p>
									<div className="flex items-center gap-x-4">
										<div className="h-[60px] w-[60px] overflow-hidden rounded-full">
											<Image
												src="/assets/img_placeholder/th-1/testimonial-img-4.jpg"
												alt="testimonial-img"
												width={60}
												height={60}
												className="h-full w-full object-cover object-center"
											/>
										</div>
										<div className="flex flex-col gap-y-1">
											<span className="block text-lg font-semibold leading-[1.6]">
												Jack Fayol
											</span>
											<span className="block text-sm font-light leading-[1.4]">
												HR Manager
											</span>
										</div>
									</div>
								</div>
								{/* Testimonial Item */}
								{/* Testimonial Item */}
								<div
									className="jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white"
									data-jos_animation="fade-right"
									data-jos_delay="0.2"
								>
									<div className="block">
										<Image
											src="/assets/img_placeholder/th-1/rating.svg"
											alt="rating"
											width={146}
											height={25}
										/>
									</div>
									<p>
										We were concerned about integrating their APIs were well
										documented, and their support team was super cool.
									</p>
									<div className="flex items-center gap-x-4">
										<div className="h-[60px] w-[60px] overflow-hidden rounded-full">
											<Image
												src="/assets/img_placeholder/th-1/testimonial-img-5.jpg"
												alt="testimonial-img"
												width={60}
												height={60}
												className="h-full w-full object-cover object-center"
											/>
										</div>
										<div className="flex flex-col gap-y-1">
											<span className="block text-lg font-semibold leading-[1.6]">
												Karen Lynn
											</span>
											<span className="block text-sm font-light leading-[1.4]">
												Software Engineer
											</span>
										</div>
									</div>
								</div>
								{/* Testimonial Item */}
								{/* Testimonial Item */}
								<div
									className="jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white"
									data-jos_animation="fade-right"
									data-jos_delay="0.3"
								>
									<div className="block">
										<Image
											src="/assets/img_placeholder/th-1/rating.svg"
											alt="rating"
											width={146}
											height={25}
										/>
									</div>
									<p>
										The return on investment has exceeded our expectations. its
										an investment in the future of our business.
									</p>
									<div className="flex items-center gap-x-4">
										<div className="h-[60px] w-[60px] overflow-hidden rounded-full">
											<Image
												src="/assets/img_placeholder/th-1/testimonial-img-6.jpg"
												alt="testimonial-img"
												width={60}
												height={60}
												className="h-full w-full object-cover object-center"
											/>
										</div>
										<div className="flex flex-col gap-y-1">
											<span className="block text-lg font-semibold leading-[1.6]">
												Henry Ochi
											</span>
											<span className="block text-sm font-light leading-[1.4]">
												Bank Manager
											</span>
										</div>
									</div>
								</div>
								{/* Testimonial Item */}
							</div>
							{/* Testimonial List */}
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Testimonial Section Start :::... */}
			</main>
			<Footer_01 />
		</>
	);
}

export default Services;
