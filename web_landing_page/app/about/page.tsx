import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import Image from "next/image";
import Link from "next/link";

function About() {
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
								<h1 className="breadcrumb-title">About Us</h1>
								<ul className="breadcrumb-nav">
									<li>
										<Link href="/">Home</Link>
									</li>
									<li>About</li>
								</ul>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Breadcrumb Section End :::... */}
				{/*...::: About Us Section Start :::... */}
				<section id="about-hero-section">
					{/* Section Spacer */}
					<div className="mb-20 lg:mb-24">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 text-center lg:mb-12 xl:mb-20">
								<div className="mx-auto md:max-w-xl lg:max-w-3xl xl:max-w-[950px]">
									<h2>We are a trusted partner in our clients AI journey</h2>
								</div>
							</div>
							{/* Section Content Block */}
							{/* About Hero Image */}
							<div
								className="jos overflow-hidden rounded-3xl"
								data-jos_animation="zoom"
							>
								<Image
									src="/assets/img_placeholder/th-1/about-hero-image.jpg"
									alt="about-hero-image"
									width={1296}
									height={650}
									className="h-full w-full object-cover"
								/>
							</div>
							{/* About Hero Image */}
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: About Us Section End :::... */}
				{/*...::: About Funfact Start :::... */}
				<section id="about-funfact-section">
					{/* Section Container */}
					<div className="global-container">
						{/* Counter Scroll */}
						<ul className="grid grid-cols-1 gap-10 gap-y-5 text-center sm:grid-cols-2 sm:text-left lg:grid-cols-4">
							{/* Counter Items */}
							<li className="jos" data-jos_delay="0.1">
								<h3
									className="text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-[80px]"
									data-module="countup"
								>
									<span className="start-number" data-countup-number={2}>
										2
									</span>
									K+
								</h3>
								<span className="block text-lg font-normal text-black">
									Successful Implementations
								</span>
							</li>
							{/* Counter Items */}
							{/* Counter Items */}
							<li className="jos" data-jos_delay="0.2">
								<h3
									className="text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-[80px]"
									data-module="countup"
								>
									<span className="start-number" data-countup-number={95}>
										95
									</span>
									%
								</h3>
								<span className="block text-lg font-normal text-black">
									Client Satisfaction Rate
								</span>
							</li>
							{/* Counter Items */}
							{/* Counter Items */}
							<li className="jos" data-jos_delay="0.3">
								<h3
									className="text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-[80px]"
									data-module="countup"
								>
									<span className="start-number" data-countup-number={40}>
										40
									</span>
									+
								</h3>
								<span className="block text-lg font-normal text-black">
									Awards and Recognitions
								</span>
							</li>
							{/* Counter Items */}
							{/* Counter Items */}
							<li className="jos" data-jos_delay="0.4">
								<h3
									className="text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-[80px]"
									data-module="countup"
								>
									<span className="start-number" data-countup-number={73}>
										73
									</span>
									+
								</h3>
								<span className="block text-lg font-normal text-black">
									Growth and Expansion
								</span>
							</li>
							{/* Counter Items */}
						</ul>
						{/* Counter Scroll */}
					</div>
					{/* Section Container */}
				</section>
				{/*...::: About Funfact Start :::... */}
				{/*...::: Content Section Start :::... */}
				<section id="content-section-2">
					{/* Section Spacer */}
					<div className="pb-20 pt-20 xl:pb-[150px] xl:pt-[130px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="grid grid-cols-1 items-center gap-12 md:grid-cols-2 xl:grid-cols-[minmax(0,_1.3fr)_1fr]">
								{/* Content Left Block */}
								<div
									className="jos order-2 overflow-hidden rounded-md"
									data-jos_animation="fade-left"
								>
									<Image
										src="/assets/img_placeholder/th-1/about-image.png"
										alt="content-image-2"
										width={526}
										height={550}
										className="h-auto w-full"
									/>
								</div>
								{/* Content Left Block */}
								{/* Content Right Block */}
								<div className="jos order-1" data-jos_animation="fade-right">
									{/* Section Content Block */}
									<div className="mb-6">
										<h2>Delivering the best solutions with AI</h2>
									</div>
									{/* Section Content Block */}
									<div className="text-lg leading-[1.4] lg:text-[21px]">
										<p className="mb-7 last:mb-0">
											Our mission is to empower businesses with AI-powered
											solutions that increase productivity, improve
											decision-making and drive growth.
										</p>
										<p className="mb-7 last:mb-0">
											Since 2016 we have been passionate about helping our
											clients harness With a team of AI experts and data
											scientists their full potential &amp; stay competitive in
											an increasingly digital world.
										</p>
										<Link
											href="/contact"
											className="button mt-5 rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white"
										>
											Get in touch
										</Link>
									</div>
								</div>
								{/* Content Right Block */}
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Content Section End :::... */}
				{/*...::: Core Value Section Start :::... */}
				<section id="core-value">
					{/* Section Spacer */}
					<div className="jos mx-5 rounded-[50px] bg-black px-[20px] py-20 sm:px-[50px] md:mx-[50px] lg:px-[100px] xl:py-[130px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="mb-10 text-center lg:mb-12 xl:mb-20">
								<div className="mx-auto md:max-w-xl lg:max-w-3xl xl:max-w-[745px]">
									<h2 className="text-white">
										The core values behind our work
									</h2>
								</div>
							</div>
							{/* Section Content Block */}
							{/* Horizontal Separator */}
							<div className="mb-6 h-[4px] w-full rounded bg-colorCodGray sm:mb-0" />
							{/* Core Value list */}
							<ul className="grid grid-cols-1 justify-between gap-6 md:grid-cols-2 xxl:flex xxl:flex-nowrap">
								{/* Core Value Item */}
								<li className="relative after:absolute after:-top-[3px] after:left-0 after:h-[5px] after:w-full after:scale-x-0 after:rounded-[5px] after:bg-colorOrangyRed after:transition-all after:duration-300 hover:after:scale-x-0 sm:pt-6 lg:pt-10 xxl:hover:after:scale-x-100">
									<div className="mb-3 flex items-center gap-x-3 md:mb-6">
										<div className="h-[30px] w-[30px]">
											<Image
												src="/assets/img_placeholder/th-1/core-value-icon-1.svg"
												alt="core-value-icon-1"
												width={30}
												height={30}
											/>
										</div>
										<h4 className="flex-1 text-white">Innovation</h4>
									</div>
									<p className="text-lg text-white lg:text-[21px]">
										We’re committed to exploring new technologies, and finding
									</p>
								</li>
								{/* Core Value Item */}
								{/* Core Value Item */}
								<li className="relative after:absolute after:-top-[3px] after:left-0 after:h-[5px] after:w-full after:scale-x-0 after:rounded-[5px] after:bg-colorOrangyRed after:transition-all after:duration-300 hover:after:scale-x-0 sm:pt-6 lg:pt-10 xxl:hover:after:scale-x-100">
									<div className="mb-3 flex items-center gap-x-3 md:mb-6">
										<div className="h-[30px] w-[30px]">
											<Image
												src="/assets/img_placeholder/th-1/core-value-icon-2.svg"
												alt="core-value-icon-2"
												width={30}
												height={30}
											/>
										</div>
										<h4 className="flex-1 text-white">Excellence</h4>
									</div>
									<p className="text-lg text-white lg:text-[21px]">
										We set high standards for our work &amp; we are dedicated
										team
									</p>
								</li>
								{/* Core Value Item */}
								{/* Core Value Item */}
								<li className="relative after:absolute after:-top-[3px] after:left-0 after:h-[5px] after:w-full after:scale-x-0 after:rounded-[5px] after:bg-colorOrangyRed after:transition-all after:duration-300 hover:after:scale-x-0 sm:pt-6 lg:pt-10 xxl:hover:after:scale-x-100">
									<div className="mb-3 flex items-center gap-x-3 md:mb-6">
										<div className="h-[30px] w-[30px]">
											<Image
												src="/assets/img_placeholder/th-1/core-value-icon-3.svg"
												alt="core-value-icon-3"
												width={30}
												height={30}
											/>
										</div>
										<h4 className="flex-1 text-white">Collaboration</h4>
									</div>
									<p className="text-lg text-white lg:text-[21px]">
										We believe in the power of collaboration, working closely
									</p>
								</li>
								{/* Core Value Item */}
								{/* Core Value Item */}
								<li className="relative after:absolute after:-top-[3px] after:left-0 after:h-[5px] after:w-full after:scale-x-0 after:rounded-[5px] after:bg-colorOrangyRed after:transition-all after:duration-300 hover:after:scale-x-0 sm:pt-6 lg:pt-10 xxl:hover:after:scale-x-100">
									<div className="mb-3 flex items-center gap-x-3 md:mb-6">
										<div className="h-[30px] w-[30px]">
											<Image
												src="/assets/img_placeholder/th-1/core-value-icon-4.svg"
												alt="core-value-icon-4"
												width={30}
												height={30}
											/>
										</div>
										<h4 className="flex-1 text-white">Integrity</h4>
									</div>
									<p className="text-lg text-white lg:text-[21px]">
										We uphold the highest ethical honesty in all our
										interactions
									</p>
								</li>
								{/* Core Value Item */}
							</ul>
							{/* Core Value list */}
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Core Value Section End :::... */}
				{/*...::: Team Section Start :::... */}
				<section id="team-section">
					{/* Section Spacer */}
					<div className="py-20 xl:py-[130px]">
						{/* Section Container */}
						<div className="global-container">
							{/* Section Content Block */}
							<div className="jos mb-10 flex flex-wrap items-center justify-between lg:mb-12 xl:mb-20">
								<div className="max-w-sm lg:max-w-3xl xl:max-w-[745px]">
									<h2>Our team consists of a group of talents</h2>
								</div>
								<Link
									href="/team"
									className="button mt-5 rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white"
								>
									Join our team
								</Link>
							</div>
							{/* Section Content Block */}
							{/* Team Member List */}
							<ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
								{/* Team Member Item */}
								<li
									className="jos rounded-[20px] bg-colorLinenRuffle p-[20px]"
									data-jos_animation="flip"
									data-jos_delay="0.1"
								>
									<div className="xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]">
										<Image
											src="/assets/img_placeholder/th-1/team-member-img-1.jpg"
											alt="team-member-img-1"
											width={376}
											height={400}
											className="h-full w-full object-cover"
										/>
									</div>
									<div className="mt-5">
										<Link
											href="/team-details"
											className="font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]"
										>
											Mr. Abraham Maslo
										</Link>
										<div className="mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center">
											<span className="text-[21px]">Chief AI Officer</span>
											<ul className="mt-auto flex gap-x-[15px]">
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.facebook.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-white.svg"
															alt="facebook"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-black.svg"
															alt="facebook"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.twitter.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-white.svg"
															alt="twitter"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-black.svg"
															alt="twitter"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.linkedin.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-white.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-black.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.instagram.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-white.svg"
															alt="instagram"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-black.svg"
															alt="instagram"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
											</ul>
										</div>
									</div>
								</li>
								{/* Team Member Item */}
								{/* Team Member Item */}
								<li
									className="jos rounded-[20px] bg-colorLinenRuffle p-[20px]"
									data-jos_animation="flip"
									data-jos_delay="0.2"
								>
									<div className="xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]">
										<Image
											src="/assets/img_placeholder/th-1/team-member-img-2.jpg"
											alt="team-member-img-2"
											width={376}
											height={400}
											className="h-full w-full object-cover"
										/>
									</div>
									<div className="mt-5">
										<Link
											href="/team-details"
											className="font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]"
										>
											Willium Robert
										</Link>
										<div className="mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center">
											<span className="text-[21px]">Data Engineer</span>
											<ul className="mt-auto flex gap-x-[15px]">
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.facebook.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-white.svg"
															alt="facebook"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-black.svg"
															alt="facebook"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.twitter.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-white.svg"
															alt="twitter"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-black.svg"
															alt="twitter"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.linkedin.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-white.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-black.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.instagram.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-white.svg"
															alt="instagram"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-black.svg"
															alt="instagram"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
											</ul>
										</div>
									</div>
								</li>
								{/* Team Member Item */}
								{/* Team Member Item */}
								<li
									className="jos rounded-[20px] bg-colorLinenRuffle p-[20px]"
									data-jos_animation="flip"
									data-jos_delay="0.3"
								>
									<div className="xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]">
										<Image
											src="/assets/img_placeholder/th-1/team-member-img-3.jpg"
											alt="team-member-img-3"
											width={376}
											height={400}
											className="h-full w-full object-cover"
										/>
									</div>
									<div className="mt-5">
										<Link
											href="/team-details"
											className="font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]"
										>
											Henry Fayol
										</Link>
										<div className="mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center">
											<span className="text-[21px]">Research Scientist</span>
											<ul className="mt-auto flex gap-x-[15px]">
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.facebook.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-white.svg"
															alt="facebook"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-black.svg"
															alt="facebook"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.twitter.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-white.svg"
															alt="twitter"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-black.svg"
															alt="twitter"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.linkedin.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-white.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-black.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.instagram.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-white.svg"
															alt="instagram"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-black.svg"
															alt="instagram"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
											</ul>
										</div>
									</div>
								</li>
								{/* Team Member Item */}
								{/* Team Member Item */}
								<li
									className="jos rounded-[20px] bg-colorLinenRuffle p-[20px]"
									data-jos_animation="flip"
									data-jos_delay="0.4"
								>
									<div className="xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]">
										<Image
											src="/assets/img_placeholder/th-1/team-member-img-4.jpg"
											alt="team-member-img-4"
											width={376}
											height={400}
											className="h-full w-full object-cover"
										/>
									</div>
									<div className="mt-5">
										<Link
											href="/team-details"
											className="font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]"
										>
											Henry Martine
										</Link>
										<div className="mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center">
											<span className="text-[21px]">AI Researchers</span>
											<ul className="mt-auto flex gap-x-[15px]">
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.facebook.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-white.svg"
															alt="facebook"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-black.svg"
															alt="facebook"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.twitter.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-white.svg"
															alt="twitter"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-black.svg"
															alt="twitter"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.linkedin.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-white.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-black.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.instagram.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-white.svg"
															alt="instagram"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-black.svg"
															alt="instagram"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
											</ul>
										</div>
									</div>
								</li>
								{/* Team Member Item */}
								{/* Team Member Item */}
								<li
									className="jos rounded-[20px] bg-colorLinenRuffle p-[20px]"
									data-jos_animation="flip"
									data-jos_delay="0.5"
								>
									<div className="xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]">
										<Image
											src="/assets/img_placeholder/th-1/team-member-img-5.jpg"
											alt="team-member-img-5"
											width={376}
											height={400}
											className="h-full w-full object-cover"
										/>
									</div>
									<div className="mt-5">
										<Link
											href="/team-details"
											className="font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]"
										>
											Jack Fox
										</Link>
										<div className="mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center">
											<span className="text-[21px]">NLP Expert</span>
											<ul className="mt-auto flex gap-x-[15px]">
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.facebook.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-white.svg"
															alt="facebook"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-black.svg"
															alt="facebook"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.twitter.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-white.svg"
															alt="twitter"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-black.svg"
															alt="twitter"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.linkedin.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-white.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-black.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.instagram.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-white.svg"
															alt="instagram"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-black.svg"
															alt="instagram"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
											</ul>
										</div>
									</div>
								</li>
								{/* Team Member Item */}
								{/* Team Member Item */}
								<li
									className="jos rounded-[20px] bg-colorLinenRuffle p-[20px]"
									data-jos_animation="flip"
									data-jos_delay="0.6"
								>
									<div className="xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]">
										<Image
											src="/assets/img_placeholder/th-1/team-member-img-6.jpg"
											alt="team-member-img-6"
											width={376}
											height={400}
											className="h-full w-full object-cover"
										/>
									</div>
									<div className="mt-5">
										<Link
											href="/team-details"
											className="font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]"
										>
											Adam Smith
										</Link>
										<div className="mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center">
											<span className="text-[21px]">Project Manager</span>
											<ul className="mt-auto flex gap-x-[15px]">
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.facebook.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-white.svg"
															alt="facebook"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/facebook-icon-black.svg"
															alt="facebook"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.twitter.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-white.svg"
															alt="twitter"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/twitter-icon-black.svg"
															alt="twitter"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.linkedin.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-white.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/linkedin-icon-black.svg"
															alt="linkedin"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
												<li>
													<Link
														rel="noopener noreferrer"
														href="http://www.instagram.com"
														className="group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed"
													>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-white.svg"
															alt="instagram"
															width={14}
															height={14}
															className="opacity-100 group-hover:opacity-0"
														/>
														<Image
															src="/assets/img_placeholder/th-1/instagram-icon-black.svg"
															alt="instagram"
															width={14}
															height={14}
															className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100"
														/>
													</Link>
												</li>
											</ul>
										</div>
									</div>
								</li>
								{/* Team Member Item */}
							</ul>
							{/* Team Member List */}
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Team Section End :::... */}
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
			<Footer_01/>
		</>
	);
}

export default About;
