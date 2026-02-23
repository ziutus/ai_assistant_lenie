import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import Image from "next/image";
import Link from "next/link";

function PortfolioDetails() {
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
								<h1 className="breadcrumb-title">Portfolio Single</h1>
								<ul className="breadcrumb-nav">
									<li>
										<Link href="/">Home</Link>
									</li>
									<li>Portfolio Single</li>
								</ul>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Breadcrumb Section End :::... */}
				{/*...::: Portfolio Details Section Start :::... */}
				<section id="portfolio-detial-section">
					{/* Section Spacer */}
					<div className="pb-20 xl:pb-[150px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 lg:mb-16 xl:mb-20">
								<div className="md:max-w-xs lg:max-w-xl xl:max-w-[846px]">
									<h2>Natural language processing models</h2>
								</div>
							</div>
							{/* Section Content Block */}
							<div
								className="jos h-80 w-full overflow-hidden rounded-[10px] lg:h-[550px]"
								data-jos_animation="zoom"
							>
								<Image
									src="/assets/img_placeholder/th-1/portfolio-main-img.jpg"
									alt="portfolio-main-img"
									width={1296}
									height={550}
									className="h-full w-full object-cover"
								/>
							</div>
							{/* Portfolio Info List */}
							<ul className="mt-[55px] grid grid-cols-1 justify-between gap-x-16 gap-y-6 sm:grid-cols-2 sm:gap-y-8 lg:flex">
								<li
									className="jos flex flex-col gap-y-2 sm:gap-y-4"
									data-jos_delay="0.1"
								>
									<span className="text-[21px] font-semibold leading-[1.4] text-[#7F8995]">
										Client:
									</span>
									<div className="text-2xl font-bold leading-[1.4] -tracking-[1px] md:text-[30px]">
										XYZ Company
									</div>
								</li>
								<li
									className="jos flex flex-col gap-y-2 sm:gap-y-4"
									data-jos_delay="0.2"
								>
									<span className="text-[21px] font-semibold leading-[1.4] text-[#7F8995]">
										Services:
									</span>
									<div className="text-2xl font-bold leading-[1.4] -tracking-[1px] md:text-[30px]">
										Web Design
									</div>
								</li>
								<li
									className="jos flex flex-col gap-y-2 sm:gap-y-4"
									data-jos_delay="0.3"
								>
									<span className="text-[21px] font-semibold leading-[1.4] text-[#7F8995]">
										Duration:
									</span>
									<div className="text-2xl font-bold leading-[1.4] -tracking-[1px] md:text-[30px]">
										2 Weeks
									</div>
								</li>
								<li
									className="jos flex flex-col gap-y-2 sm:gap-y-4"
									data-jos_delay="0.4"
								>
									<span className="text-[21px] font-semibold leading-[1.4] text-[#7F8995]">
										Website
									</span>
									<div className="text-2xl font-bold leading-[1.4] -tracking-[1px] md:text-[30px]">
										<Link
											rel="noopener noreferrer"
											href="https://www.example.com"
											className="flex items-center gap-x-[10px] hover:text-colorOrangyRed"
										>
											Live preview
											<div className="h-9 w-9">
												<Image
													src="/assets/img_placeholder/th-1/icon-black-long-arrow-right.svg"
													alt="icon-black-long-arrow-right"
													width={35}
													height={35}
													className="h-auto w-9"
												/>
											</div>
										</Link>
									</div>
								</li>
							</ul>
							{/* Portfolio Info List */}
							{/* Horizontal Separator */}
							<div className="my-10 h-[1px] w-full bg-[#EAEDF0] lg:my-20" />
							{/* Horizontal Separator */}
							<div className="flex flex-col gap-y-10 lg:gap-y-20">
								{/* Content Block */}
								<div className="grid grid-cols-1 items-center gap-[30px] lg:grid-cols-2">
									{/* Content Left Block */}
									<div
										className="jos order-2 overflow-hidden rounded-md lg:order-1"
										data-jos_animation="fade-right"
									>
										<Image
											src="/assets/img_placeholder/th-1/content-image-5.jpg"
											alt="content-image-6"
											width={636}
											height={400}
											className="h-auto w-full"
										/>
									</div>
									{/* Content Left Block */}
									{/* Content Right Block */}
									<div
										className="jos order-1 lg:order-2"
										data-jos_animation="fade-left"
									>
										{/* Section Content Block */}
										<div className="mb-4 xl:mb-6">
											<h2>Project overview</h2>
										</div>
										{/* Section Content Block */}
										<span className="mb-8 block text-2xl font-bold leading-snug">
											Machine Learning and Predictive Analytics:
										</span>
										<ul className="mb-7 flex flex-col gap-y-[30px] text-lg leading-[1.4] last:mb-0 lg:text-[21px]">
											<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[6px] after:w-[6px] after:rounded-[50%] after:bg-black">
												Demand Forecasting: AI SaaS helps businesses predict
												demand for products and services, optimizing inventory
												management and supply chain operations.
											</li>
											<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[6px] after:w-[6px] after:rounded-[50%] after:bg-black">
												Customer Churn Prediction: It s used to identify
												customers at risk of leaving a service or product,
												allowing proactive retention efforts.
											</li>
										</ul>
									</div>
									{/* Content Right Block */}
								</div>
								{/* Content Block */}
								{/* Content Block */}
								<div className="grid grid-cols-1 items-center gap-[30px] lg:grid-cols-2">
									{/* Content Left Block */}
									<div
										className="jos order-2 overflow-hidden rounded-md lg:order-2"
										data-jos_animation="fade-left"
									>
										<Image
											src="/assets/img_placeholder/th-1/content-image-6.jpg"
											alt="content-image-6"
											width={636}
											height={400}
											className="h-auto w-full"
										/>
									</div>
									{/* Content Left Block */}
									{/* Content Right Block */}
									<div
										className="jos order-1 lg:order-1"
										data-jos_animation="fade-right"
									>
										{/* Section Content Block */}
										<div className="mb-4 xl:mb-6">
											<h2>Project results</h2>
										</div>
										{/* Section Content Block */}
										<span className="mb-8 block text-2xl font-bold leading-snug">
											Natural Language Processing (NLP):
										</span>
										<ul className="mb-7 flex flex-col gap-y-[30px] text-lg leading-[1.4] last:mb-0 lg:text-[21px]">
											<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[6px] after:w-[6px] after:rounded-[50%] after:bg-black">
												Text Analysis: AI SaaS can be used to analyze text data
												for sentiment analysis, entity recognition, language
												translation, and text summarization.
											</li>
											<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[6px] after:w-[6px] after:rounded-[50%] after:bg-black">
												Chatbots and Virtual Assistants: Businesses use AI SaaS
												to build chatbots and virtual assistants for customer
												support, improving response times and efficiency.
											</li>
										</ul>
									</div>
									{/* Content Right Block */}
								</div>
								{/* Content Block */}
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Portfolio Details Section End :::... */}
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
									data-jos_animation="fade-right"
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
									{/* Section Content Block */}
									<div className="mb-6 md:max-w-max">
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

export default PortfolioDetails;
