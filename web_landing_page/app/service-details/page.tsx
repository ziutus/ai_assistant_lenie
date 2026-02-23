"use client";
import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import FsLightbox from "fslightbox-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

function ServiceDetails() {
	// To open the lightbox change the value of the "toggler" prop.
	const [toggler, setToggler] = useState(false);

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
								<h1 className="breadcrumb-title">Data Analytics</h1>
								<ul className="breadcrumb-nav">
									<li>
										<Link href="/">Home</Link>
									</li>
									<li>
										<Link href="/services">Services</Link>
									</li>
									<li>Service Details</li>
								</ul>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Breadcrumb Section End :::... */}
				{/*...::: Content Section Start :::... */}
				<section id="content-section-1">
					{/* Section Spacer */}
					<div className="pb-20 xl:pb-[150px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="grid grid-cols-1 items-center gap-12 md:grid-cols-2 xl:grid-cols-[minmax(0,_1.2fr)_1fr] xl:gap-28">
								{/* Content Left Block */}
								<div
									className="jos order-2 overflow-hidden rounded-md"
									data-jos_animation="fade-left"
								>
									<Image
										src="/assets/img_placeholder/th-1/content-image-1.jpg"
										alt="content-image-2"
										width={526}
										height={450}
										className="h-auto w-full"
									/>
								</div>
								{/* Content Left Block */}
								{/* Content Right Block */}
								<div className="jos order-1" data-jos_animation="fade-right">
									{/* Section Content Block */}
									<div className="mb-6">
										<h2>Analyze any data perfectly with AI</h2>
									</div>
									{/* Section Content Block */}
									<div className="text-lg leading-[1.4] lg:text-[21px]">
										<p className="mb-7 last:mb-0">
											AI data analysis, also known as artificial intelligence
											data analysis or AI-driven data analysis, refers to the
											process of using artificial intelligence and machine
											learning techniques.
										</p>
									</div>
									<ul className="mt-8 grid gap-x-6 gap-y-8 sm:grid-cols-2 md:grid-cols-1 xl:mt-14 xl:grid-cols-2">
										<li className="flex flex-col gap-y-4">
											<div className="h-[50px] w-[50px]">
												<Image
													src="/assets/img_placeholder/th-1/trending-up-icon.svg"
													alt="trending-up-icon"
													width={50}
													height={50}
													className="h-full w-full object-cover"
												/>
											</div>
											<h5>Data Preprocessing</h5>
											<p className="text-lg">
												AI data analysis can begin, and raw data must be
												collected, cleaned.
											</p>
										</li>
										<li className="flex flex-col gap-y-4">
											<div className="h-[50px] w-[50px]">
												<Image
													src="/assets/img_placeholder/th-1/cog-icon.svg"
													alt="cog-icon"
													width={50}
													height={50}
													className="h-full w-full object-cover"
												/>
											</div>
											<h5>Predictive Analytics</h5>
											<p className="text-lg">
												Algorithms use historical data to forecast future
												trends, behaviors.
											</p>
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
				{/*...::: Content Section End :::... */}
				{/*...::: Content Section Start :::... */}
				<section id="content-section-2">
					{/* Section Spacer */}
					<div className="pb-20 xl:pb-[150px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 text-center lg:mb-16 xl:mb-20">
								<div className="mx-auto md:max-w-xl lg:max-w-4xl xl:max-w-[950px]">
									<h2>Widely used throughout the industry for work</h2>
								</div>
							</div>
							{/* Section Content Block */}
							<div className="grid grid-cols-1 items-center gap-12 md:grid-cols-[minmax(0,_1fr)_1.2fr] xl:gap-28 xxl:gap-32">
								{/* Content Left Block */}
								<div
									className="jos order-2 overflow-hidden rounded-md md:order-1"
									data-jos_animation="fade-left"
								>
									<Image
										src="/assets/img_placeholder/th-1/content-image-4.jpg"
										alt="content-image-4"
										width={529}
										height={500}
										className="h-auto w-full"
									/>
								</div>
								{/* Content Left Block */}
								{/* Content Right Block */}
								<div
									className="jos order-1 md:order-2"
									data-jos_animation="fade-right"
								>
									<ul className="flex flex-col gap-y-6">
										<li>
											<h5 className="mb-[10px]">
												1. Businesses and Corporations:
											</h5>
											<p className="mb-7 last:mb-0">
												Businesses use AI data analysis to gain competitive
												advantages, optimize operations, &amp; make data-driven
												decisions. This includes industries such as retail,
												finance, manufacturing.
											</p>
										</li>
										<li>
											<h5 className="mb-[10px]">
												2. Data Scientists and Analysts:
											</h5>
											<p className="mb-7 last:mb-0">
												Data scientists and analysts leverage AI tools and
												algorithms to extract actionable insights from large
												datasets. They alsouse AI for predictive modeling,
												anomaly detection, and data visualization.
											</p>
										</li>
										<li>
											<h5 className="mb-[10px]">
												3. Government and Public Sector:
											</h5>
											<p className="mb-7 last:mb-0">
												Government agencies use AI data analysis for various
												purposes, including public policy development, law
												enforcement, urban planning, and disaster.
											</p>
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
				{/*...::: Content Section End :::... */}
				{/*...::: Funfact Section Start :::... */}
				<section id="funfact-section">
					<div className="mx-auto max-w-[1500px] px-5">
						<div className="jos grid grid-cols-1 overflow-hidden rounded-[30px] bg-black lg:rounded-[50px] xl:grid-cols-[minmax(400px,_1fr)_1.5fr] xxl:grid-cols-[1fr_minmax(800px,_1fr)]">
							{/* Funfact Left Block */}
							<div className="relative overflow-hidden rounded-[30px] lg:rounded-[50px]">
								<Image
									src="/assets/img_placeholder/th-1/funfact-image.jpg"
									alt="funfact-image"
									width={721}
									height={784}
									className="h-80 w-full object-cover object-center lg:h-[35rem] xl:h-full"
								/>
								{/* Video Play Button */}
								<button className="absolute left-1/2 top-1/2 z-[1] -translate-x-1/2 -translate-y-1/2">
									<div
										onClick={() => setToggler(!toggler)}
										className="relative flex h-[120px] w-[120px] items-center justify-center rounded-full border-[3px] border-black text-lg font-bold backdrop-blur-[2px] transition-all duration-300 hover:bg-colorOrangyRed hover:text-white"
									>
										Play
										<div className="absolute -z-[1] h-[110%] w-[110%] animate-[ping_1.5s_ease-in-out_infinite] rounded-full bg-gray-600 opacity-30"></div>
									</div>
								</button>
								{/* Video Play Button */}
							</div>
							<FsLightbox
								toggler={toggler}
								sources={["https://www.youtube.com/watch?v=3nQNiWdeH2Q"]}
							/>
							{/* Funfacct Left Block */}
							{/* Funfact Right Block */}
							<div className="self-center px-6 py-16 sm:py-20 md:px-16 xl:px-10 xl:py-24 xxl:py-32 xxl:pl-16 xxl:pr-28">
								{/* Section Content Block */}
								<div className="mb-8 lg:mb-16 xl:mb-6">
									<h2 className="text-white">
										AI-powered that streamline tasks
									</h2>
								</div>
								{/* Section Content Block */}
								<div className="text-left text-lg leading-[1.4] text-white lg:text-[21px]">
									<p className="mb-7 last:mb-0">
										As your business grows or your AI SaaS needs change, you can
										easily adjust your subscription level to match those needs.
										This flexibility ensures that AI remains an asset.
									</p>
								</div>
								{/* Horizontal Separator */}
								<div className="my-14 h-[1px] w-full bg-colorCodGray" />
								{/* Counter Scroll */}
								<ul className="flex flex-col justify-center gap-x-11 gap-y-8 text-center sm:flex-row md:text-left xl:justify-normal xl:text-left xxl:gap-x-20">
									{/* Counter Items */}
									<li>
										<h3
											className="text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-7xl xxl:text-[120px]"
											data-module="countup"
										>
											<span className="start-number" data-countup-number={92}>
												92
											</span>
											%
										</h3>
										<span className="block text-lg font-normal text-white lg:text-[21px]">
											Customer service inquiries
										</span>
									</li>
									{/* Counter Items */}
									{/* Counter Items */}
									<li>
										<h3
											className="text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-7xl xxl:text-[120px]"
											data-module="countup"
										>
											<span className="start-number" data-countup-number={75}>
												75
											</span>
											%
										</h3>
										<span className="block text-lg font-normal text-white lg:text-[21px]">
											Using financial institutions
										</span>
									</li>
									{/* Counter Items */}
								</ul>
								{/* Counter Scroll */}
							</div>
							{/* Funfact Right Block */}
						</div>
					</div>
				</section>
				{/*...::: Funfact Section End :::... */}
				{/*...::: Content Section Start :::... */}
				<section id="content-section-3">
					{/* Section Spacer */}
					<div className="pb-20 pt-20 xl:pb-[150px] xl:pt-[130px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="grid grid-cols-1 items-center gap-12 md:grid-cols-2 xl:grid-cols-[minmax(0,_1.2fr)_1fr] xl:gap-28">
								{/* Content Left Block */}
								<div
									className="jos order-2 overflow-hidden rounded-md"
									data-jos_animation="fade-left"
								>
									<Image
										src="/assets/img_placeholder/th-1/content-image-1.jpg"
										alt="content-image-2"
										width={526}
										height={450}
										className="h-auto w-full"
									/>
								</div>
								{/* Content Left Block */}
								{/* Content Right Block */}
								<div className="jos order-1" data-jos_animation="fade-right">
									{/* Section Content Block */}
									<div className="mb-6">
										<h2>Manage large amounts of data</h2>
									</div>
									{/* Section Content Block */}
									<div className="text-lg leading-[1.4] lg:text-[21px]">
										<p className="mb-7 last:mb-0">
											AI data analysis also can handle vast amounts of data,
											making it suitable for big data environments. Data
											analysis can automate many aspects of data processing and
											analysis
										</p>
									</div>
									<ul className="mt-8 grid gap-x-6 gap-y-8 sm:grid-cols-2 md:grid-cols-1 xl:mt-14 xl:grid-cols-2">
										<li className="flex flex-col gap-y-4">
											<div className="h-[50px] w-[50px]">
												<Image
													src="/assets/img_placeholder/th-1/icon-orange-clock.svg"
													alt="trending-up-icon"
													width={50}
													height={50}
													className="h-full w-full object-cover"
												/>
											</div>
											<h5>Real-Time Analysis</h5>
											<p className="text-lg">
												Some AI data analysis solutions are design to process
												making instant.
											</p>
										</li>
										<li className="flex flex-col gap-y-4">
											<div className="h-[50px] w-[50px]">
												<Image
													src="/assets/img_placeholder/th-1/icon-orange-cursor-click.svg"
													alt="cog-icon"
													width={50}
													height={50}
													className="h-full w-full object-cover"
												/>
											</div>
											<h5>Automation</h5>
											<p className="text-lg">
												his leads to increased efficiency and quicker
												decision-making.
											</p>
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
				{/*...::: Content Section End :::... */}
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
			<Footer_01 />
		</>
	);
}

export default ServiceDetails;
