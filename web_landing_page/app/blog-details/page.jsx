import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import Image from "next/image";
import Link from "next/link";

function BlogDetails() {
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
								<h1 className="breadcrumb-title">Blog Details</h1>
								<ul className="breadcrumb-nav">
									<li>
										<Link href="/">Home</Link>
									</li>
									<li>Blog Details</li>
								</ul>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Breadcrumb Section End :::... */}
				{/*...::: Blog Section Start :::... */}
				<div className="blog-section">
					{/* Section Spacer */}
					<div className="pb-40 xl:pb-[220px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="grid grid-cols-1 gap-x-6 gap-y-10 lg:grid-cols-[1fr,minmax(416px,_0.5fr)]">
								<div className="flex flex-col gap-y-10 lg:gap-y-14 xl:gap-y-20">
									{/* Blog Post Details */}
									<div className="flex flex-col gap-6">
										{/* Blog Post Text Area */}
										<article className="jos overflow-hidden bg-white">
											<div className="mb-7 block overflow-hidden rounded-[10px]">
												<Image
													src="/assets/img_placeholder/th-1/blog-main-1.jpg"
													alt="blog-main-1"
													width={856}
													height={540}
													className="h-auto w-full scale-100 object-cover"
												/>
											</div>
											{/* Blog Post Meta */}
											<ul className="flex flex-wrap items-center gap-6">
												<li className="relative font-semibold after:absolute after:left-full after:top-1/2 after:h-[7px] after:w-[7px] after:-translate-y-1/2 after:translate-x-2 after:rounded-full after:bg-colorCodGray last:after:hidden">
													<Link
														href="/blog-details"
														className="hover:text-colorOrangyRed"
													>
														Business
													</Link>
												</li>
												<li className="relative font-semibold after:absolute after:left-full after:top-1/2 after:h-[7px] after:w-[7px] after:-translate-y-1/2 after:translate-x-2 after:rounded-full after:bg-colorCodGray last:after:hidden">
													<Link
														href="/blog-details"
														className="hover:text-colorOrangyRed"
													>
														June 12, 2024
													</Link>
												</li>
											</ul>
											{/* Blog Post Meta */}
											<h5 className="mb-3 mt-5">
												10 ways to supercharge your startup with AI integration:
												unlock exponential growth
											</h5>
											<p className="mb-7 last:mb-0">
												The rapid advancements in AI have paved the way for
												startups to revolutionize their businesses. This article
												explores 10 key ways AI can be integrated into startups
												and provides real-world examples of its tangible impact
												across industries.
											</p>
											<ul className="mb-7 flex flex-col gap-7 last:mb-0">
												<li>
													<div className="font-semibold">
														1. AI-Powered Customer Support
													</div>
													<p className="mb-7 last:mb-0">
														AI chatbots and virtual assistants can handle
														routine queries, troubleshoot issues, and guide
														users, improving response times. This frees up human
														agents to tackle complex tasks, enhancing user
														experience.
													</p>
												</li>
												<li>
													<div className="font-semibold">
														2. Predictive Maintenance
													</div>
													<p className="mb-7 last:mb-0">
														By analyzing usage patterns, ML algorithms can
														predict failures, enabling proactive maintenance and
														minimizing downtime.
													</p>
												</li>
												<li>
													<div className="font-semibold">
														3. Enhanced Cybersecurity
													</div>
													<p className="mb-7 last:mb-0">
														AI anomaly detection, behavior analysis, and
														intrusion prevention boost security and data
														protection. This safeguards infrastructure and
														builds user trust.
													</p>
												</li>
												<li>
													<div className="overflow-hidden rounded-[10px]">
														<Image
															src="/assets/img_placeholder/th-1/blog-inner-image.jpg"
															alt="blog-inner-image"
															width={100}
															height={100}
															className="h-auto w-full"
														/>
													</div>
												</li>
												<li>
													<div className="font-semibold">
														4. Personalized User Experiences
													</div>
													<p className="mb-7 last:mb-0">
														By analyzing behavior and preferences, AI tailors
														interfaces and features. This improves satisfaction
														and encourages retention.
													</p>
												</li>
												<li>
													<div className="font-semibold">
														5. Automated Workflows
													</div>
													<p className="mb-7 last:mb-0">
														Automating tasks like software updates and license
														management with AI reduces manual efforts and
														minimizes errors.
													</p>
												</li>
											</ul>
											<div className="font-semibold">
												Key Takeaways for Founders
											</div>
											<ul className="mb-7 last:mb-0">
												<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[5px] after:w-[5px] after:rounded-[50%] after:bg-black">
													Start with chatbot, workflow automation, and basic
													analytics.
												</li>
												<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[5px] after:w-[5px] after:rounded-[50%] after:bg-black">
													Gradually scale AI adoption as the business matures.
												</li>
												<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[5px] after:w-[5px] after:rounded-[50%] after:bg-black">
													Identify the right AI use cases to solve pressing
													needs.
												</li>
												<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[5px] after:w-[5px] after:rounded-[50%] after:bg-black">
													Integrate AI into workflows and processes seamlessly.
												</li>
												<li className="relative pl-[30px] after:absolute after:left-[10px] after:top-3 after:h-[5px] after:w-[5px] after:rounded-[50%] after:bg-black">
													Get creative — leverage partnerships and talent from
													outside.
												</li>
											</ul>
											<p className="mb-7 last:mb-0">
												The key to startup success is focusing AI efforts on the
												applications that will differentiate your business and
												have the biggest impact at each stage of growth. With
												the right strategy, AI can unlock transformation
												opportunities and exponential value creation.
											</p>
											<p className="mb-7 last:mb-0">Thanks for reading ❤</p>
										</article>
										{/* Blog Post Text Area */}
										{/* Blog Events */}
										<div className="jos flex justify-between gap-x-8">
											<div className="flex items-center gap-x-6">
												<button className="inline-flex items-center gap-x-1 text-[#121212]">
													<Image
														src="/assets/img_placeholder/th-1/icon-black-outline-thumb-up.svg"
														alt="icon-black-outline-thumb-up"
														width={24}
														height={24}
													/>
													200
												</button>
												<button className="inline-flex items-center gap-x-1 text-[#121212]">
													<Image
														src="/assets/img_placeholder/th-1/icon-black-outline-chat-alt.svg"
														alt="icon-black-outline-chat-alt"
														width={24}
														height={24}
													/>
													15
												</button>
											</div>
											<div className="flex items-center gap-x-6">
												<button className="inline-flex items-center gap-x-1 text-[#121212]">
													<Image
														src="/assets/img_placeholder/th-1/icon-black-outline-share.svg"
														alt="icon-black-outline-share"
														width={24}
														height={24}
													/>
												</button>
												<button className="inline-flex items-center gap-x-1 text-[#121212]">
													<Image
														src="/assets/img_placeholder/th-1/icon-black-outline-inbox-in.svg"
														alt="icon-black-outline-inbox-in"
														width={24}
														height={24}
													/>
												</button>
											</div>
										</div>
										{/* Blog Events */}
										{/* Horizontal Separator */}
										<div className="jos my-[30px] h-[1px] w-full bg-[#EAEDF0]" />
										{/* Horizontal Separator */}
										{/* Single Post Navigation */}
										<div className="jos flex flex-col justify-between md:flex-row md:gap-x-10 xl:gap-x-24 xxl:gap-x-[196px]">
											<Link href="/blog-details" className="group text-left">
												<span className="inline-flex items-center gap-x-3 text-[21px] font-bold transition-all duration-300 group-hover:text-colorOrangyRed">
													<Image
														src="/assets/img_placeholder/th-1/icon-black-cheveron-left.svg"
														alt="icon-black-cheveron-left.svg"
														width={24}
														height={24}
													/>
													Previous post
												</span>
												<p>
													Amazon testing AI tools to improve product
													descriptions: a game-changer
												</p>
											</Link>
											<Link href="/blog-details" className="group text-right">
												<span className="inline-flex flex-row-reverse items-center gap-x-3 text-[21px] font-bold transition-all duration-300 group-hover:text-colorOrangyRed">
													<Image
														src="/assets/img_placeholder/th-1/icon-black-cheveron-right.svg"
														alt="icon-black-cheveron-right.svg"
														width={24}
														height={24}
													/>
													Next post
												</span>
												<p>
													3 best AI businesses to make money with in 2024
													everyone is buzzing
												</p>
											</Link>
										</div>
										{/* Single Post Navigation */}
										{/* Blog Comment */}
										<div className="jos">
											<div className="mb-6 text-[24px] font-bold">
												2 comments on this post:
											</div>
											<ul className="flex flex-col gap-y-[30px]">
												{/* Single Comment List */}
												<li className="border-b border-[#EAEDF0] last:border-b-0">
													<div className="flex gap-x-5">
														{/* Comment User Image */}
														<div className="h-[80px] w-[80px] overflow-hidden rounded-full">
															<Image
																src="/assets/img_placeholder/th-1/blog-comment-large-user-img-1.jpg"
																alt="blog-comment-large-user-img-1"
																width={80}
																height={80}
															/>
														</div>
														{/* Comment User Image */}
														{/* Comment Content */}
														<div className="flex flex-1 flex-col gap-y-4">
															{/* Comment User info */}
															<div className="flex items-center justify-between gap-x-5">
																<div className="flex flex-col gap-y-1">
																	<div className="font-bold">Ricky Smith</div>
																	<div className="text-sm">June 14, 2024</div>
																</div>
																<button className="font-bold transition-all duration-300 hover:text-colorOrangyRed">
																	Reply
																</button>
															</div>
															{/* Comment User info */}
															{/* Comment User Text */}
															<p className="max-w-[616px]">
																It is a long established fact that a reader will
																be distrac readable content of a page when
																looking at its layout. The point of using is
																that it has two.
															</p>
															{/* Comment User Text */}
														</div>
														{/* Comment Content */}
													</div>
													{/* Comment Reply */}
													<ul className="mt-[30px] flex flex-col pl-8 sm:pl-32">
														{/* Comment Reply Item */}
														<li className="border-t border-[#EAEDF0] py-[30px]">
															<div className="flex gap-x-5">
																{/* Comment User Image */}
																<div className="h-[50px] w-[50px] overflow-hidden rounded-full">
																	<Image
																		src="/assets/img_placeholder/th-1/blog-comment-small-user-img-1.jpg"
																		alt="blog-comment-large-user-img-1"
																		width={50}
																		height={50}
																	/>
																</div>
																{/* Comment User Image */}
																{/* Comment Content */}
																<div className="flex flex-1 flex-col gap-y-4">
																	{/* Comment User info */}
																	<div className="flex items-center justify-between gap-x-5">
																		<div className="flex flex-col gap-y-1">
																			<div className="font-bold">
																				Joshua Jones
																			</div>
																			<div className="text-sm">
																				June 15, 2024
																			</div>
																		</div>
																		<button className="font-bold transition-all duration-300 hover:text-colorOrangyRed">
																			Reply
																		</button>
																	</div>
																	{/* Comment User info */}
																	{/* Comment User Text */}
																	<p className="max-w-[536px]">
																		It is a long established fact that a reader
																		will be distra readable content of a page
																		when looking its layout. The point of using.
																	</p>
																	{/* Comment User Text */}
																</div>
																{/* Comment Content */}
															</div>
														</li>
														{/* Comment Reply Item */}
													</ul>
													{/* Comment Reply */}
												</li>
												{/* Single Comment List */}
											</ul>
										</div>
									</div>
									{/* Blog Post Details */}
									{/* Blog Comment Form */}
									<div className="jos">
										<div className="mb-6 text-[24px] font-bold">
											Leave a comment:
										</div>
										<div className="order-1 block rounded-lg bg-white px-[30px] py-[50px] shadow-[0_4px_60px_0_rgba(0,0,0,0.1)] md:order-2">
											{/* Comment Form */}
											<form
												action="#"
												method="post"
												className="flex flex-col gap-y-5"
											>
												{/* Form Group */}
												<div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
													{/* Form Single Input */}
													<div className="flex flex-col gap-y-[10px]">
														<label
															htmlFor="comment-name"
															className="text-lg font-bold leading-[1.6]"
														>
															Enter your name
														</label>
														<input
															type="text"
															name="comment-name"
															id="comment-name"
															placeholder="Adam Smith"
															className="placeholder:[#7F8995] rounded-[10px] border border-gray-300 bg-white px-6 py-[18px] font-semibold text-black outline-none transition-all focus:border-colorOrangyRed"
															required=""
														/>
													</div>
													{/* Form Single Input */}
													{/* Form Single Input */}
													<div className="flex flex-col gap-y-[10px]">
														<label
															htmlFor="comment-email"
															className="text-lg font-bold leading-[1.6]"
														>
															Email address
														</label>
														<input
															type="email"
															name="comment-email"
															id="comment-email"
															placeholder="example@gmail.com"
															className="placeholder:[#7F8995] rounded-[10px] border border-gray-300 bg-white px-6 py-[18px] font-semibold text-black outline-none transition-all focus:border-colorOrangyRed"
															required=""
														/>
													</div>
													{/* Form Single Input */}
												</div>
												{/* Form Group */}
												{/* Form Group */}
												<div className="grid grid-cols-1 gap-6">
													{/* Form Single Input */}
													<div className="flex flex-col gap-y-[10px]">
														<label
															htmlFor="comment-message"
															className="text-lg font-bold leading-[1.6]"
														>
															Message
														</label>
														<textarea
															name="comment-message"
															id="comment-message"
															className="placeholder:[#7F8995] min-h-[180px] rounded-[10px] border border-gray-300 bg-white px-6 py-[18px] font-semibold text-black outline-none transition-all focus:border-colorOrangyRed"
															placeholder="Write your message here..."
															required=""
															defaultValue={"                            "}
														/>
													</div>
													{/* Form Single Input */}
												</div>
												<div className="">
													<button
														type="submit"
														className="button mt-5 rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white"
													>
														Send your message
													</button>
												</div>
												{/* Form Group */}
											</form>
											{/* Comment Form */}
										</div>
									</div>
									{/* Blog Comment Form */}
								</div>
								{/* Blog Aside */}
								<aside className="jos flex flex-col gap-y-[30px]">
									{/* Single Sidebar */}
									<div>
										{/* Sidebar Search */}
										<form
											action="#"
											method="post"
											className="relative h-[60px]"
										>
											<input
												type="search"
												name="sidebar-search"
												id="sidebar-search"
												placeholder="Type to search..."
												className="h-full w-full rounded-[50px] border border-[#E1E1E1] bg-white py-[15px] pl-16 pr-8 text-lg outline-none transition-all focus:border-colorOrangyRed"
												required=""
											/>
											<button
												type="submit"
												className="absolute left-[30px] top-0 h-full"
											>
												<Image
													src="/assets/img_placeholder/th-1/icon-black-search.svg"
													alt="search"
													width={20}
													height={20}
												/>
											</button>
										</form>
										{/* Sidebar Search */}
									</div>
									{/* Single Sidebar */}
									{/* Single Sidebar */}
									<div className="rounded-[10px] border border-[#EAEDF0] p-8">
										<div className="relative mb-[30px] inline-block pb-[10px] text-lg font-semibold after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-full after:bg-black">
											Blog Categories
										</div>
										{/* Blog Categories List */}
										<ul>
											<li className="mb-6 last:mb-0">
												<Link
													href="/blog-details"
													className="text-black hover:text-colorOrangyRed"
												>
													Business &amp; Marketing (18)
												</Link>
											</li>
											<li className="mb-6 last:mb-0">
												<Link
													href="/blog-details"
													className="text-black hover:text-colorOrangyRed"
												>
													Technology (05)
												</Link>
											</li>
											<li className="mb-6 last:mb-0">
												<Link
													href="/blog-details"
													className="text-black hover:text-colorOrangyRed"
												>
													Art &amp; Beauty (23)
												</Link>
											</li>
											<li className="mb-6 last:mb-0">
												<Link
													href="/blog-details"
													className="text-black hover:text-colorOrangyRed"
												>
													Digital Agency (10)
												</Link>
											</li>
										</ul>
										{/* Blog Categories List */}
									</div>
									{/* Single Sidebar */}
									{/* Single Sidebar */}
									<div className="rounded-[10px] border border-[#EAEDF0] p-8">
										<div className="relative mb-[30px] inline-block pb-[10px] text-lg font-semibold after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-full after:bg-black">
											Recent Posts
										</div>
										{/* Blog Recent Post List */}
										<ul className="flex flex-col gap-y-6">
											<li className="group flex flex-col items-center gap-x-4 gap-y-4 sm:flex-row">
												<Link
													href="/blog-details"
													className="inline-block h-[150px] w-full overflow-hidden rounded-[5px] sm:h-[100px] sm:w-[150px]"
												>
													<Image
														src="/assets/img_placeholder/th-1/blog-recent-img-1.jpg"
														alt="blog-recent-img-1"
														width={150}
														height={130}
														className="h-full w-full scale-100 object-cover transition-all duration-300 group-hover:scale-105"
													/>
												</Link>
												<div className="flex w-full flex-col gap-y-3 sm:w-auto sm:flex-1">
													<Link
														href="/blog-details"
														className="flex items-center gap-[10px] text-sm hover:text-colorOrangyRed"
													>
														<div className="h-6 w-6">
															<Image
																src="/assets/img_placeholder/th-1/icon-black-calendar.svg"
																alt="icon-black-calendar"
																width={24}
																height={24}
																className="h-full w-full object-cover"
															/>
														</div>
														June 12, 2024
													</Link>
													<Link
														href="/blog-details"
														className="text-base font-bold hover:text-colorOrangyRed"
													>
														6 profitable AI tech businesses to start
													</Link>
												</div>
											</li>
											<li className="group flex flex-col items-center gap-x-4 gap-y-4 sm:flex-row">
												<Link
													href="/blog-details"
													className="inline-block h-[150px] w-full overflow-hidden rounded-[5px] sm:h-[100px] sm:w-[150px]"
												>
													<Image
														src="/assets/img_placeholder/th-1/blog-recent-img-2.jpg"
														alt="blog-recent-img-2"
														width={150}
														height={130}
														className="h-full w-full scale-100 object-cover transition-all duration-300 group-hover:scale-105"
													/>
												</Link>
												<div className="flex w-full flex-col gap-y-3 sm:w-auto sm:flex-1">
													<Link
														href="/blog-details"
														className="flex items-center gap-[10px] text-sm hover:text-colorOrangyRed"
													>
														<div className="h-6 w-6">
															<Image
																src="/assets/img_placeholder/th-1/icon-black-calendar.svg"
																alt="icon-black-calendar"
																width={24}
																height={24}
																className="h-full w-full object-cover"
															/>
														</div>
														June 13, 2024
													</Link>
													<Link
														href="/blog-details"
														className="text-base font-bold hover:text-colorOrangyRed"
													>
														Why i decided to sell my B2B SaaS AI business
													</Link>
												</div>
											</li>
											<li className="group flex flex-col items-center gap-x-4 gap-y-4 sm:flex-row">
												<Link
													href="/blog-details"
													className="inline-block h-[150px] w-full overflow-hidden rounded-[5px] sm:h-[100px] sm:w-[150px]"
												>
													<Image
														src="/assets/img_placeholder/th-1/blog-recent-img-3.jpg"
														alt="blog-recent-img-3"
														width={150}
														height={130}
														className="h-full w-full scale-100 object-cover transition-all duration-300 group-hover:scale-105"
													/>
												</Link>
												<div className="flex w-full flex-col gap-y-3 sm:w-auto sm:flex-1">
													<Link
														href="/blog-details"
														className="flex items-center gap-[10px] text-sm hover:text-colorOrangyRed"
													>
														<div className="h-6 w-6">
															<Image
																src="/assets/img_placeholder/th-1/icon-black-calendar.svg"
																alt="icon-black-calendar"
																width={24}
																height={24}
																className="h-full w-full object-cover"
															/>
														</div>
														June 07, 2024
													</Link>
													<Link
														href="/blog-details"
														className="text-base font-bold hover:text-colorOrangyRed"
													>
														8 AI tools that will your streamline workflows
													</Link>
												</div>
											</li>
										</ul>
										{/* Blog Recent Post List */}
									</div>
									{/* Single Sidebar */}
									{/* Single Sidebar */}
									<div className="rounded-[10px] border border-[#EAEDF0] p-8">
										<div className="relative mb-[30px] inline-block pb-[10px] text-lg font-semibold after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-full after:bg-black">
											Tags
										</div>
										{/* Blog Tags Post List */}
										<ul className="flex flex-wrap gap-x-2 gap-y-4">
											<li>
												<Link
													href="/blog-details"
													className="inline-block rounded-[55px] bg-black bg-opacity-5 px-5 py-1 hover:bg-colorOrangyRed hover:text-white"
												>
													Article
												</Link>
											</li>
											<li>
												<Link
													href="/blog-details"
													className="inline-block rounded-[55px] bg-black bg-opacity-5 px-5 py-1 hover:bg-colorOrangyRed hover:text-white"
												>
													Business
												</Link>
											</li>
											<li>
												<Link
													href="/blog-details"
													className="inline-block rounded-[55px] bg-black bg-opacity-5 px-5 py-1 hover:bg-colorOrangyRed hover:text-white"
												>
													Digital
												</Link>
											</li>
											<li>
												<Link
													href="/blog-details"
													className="inline-block rounded-[55px] bg-black bg-opacity-5 px-5 py-1 hover:bg-colorOrangyRed hover:text-white"
												>
													Technology
												</Link>
											</li>
											<li>
												<Link
													href="/blog-details"
													className="inline-block rounded-[55px] bg-black bg-opacity-5 px-5 py-1 hover:bg-colorOrangyRed hover:text-white"
												>
													UI/UX
												</Link>
											</li>
										</ul>
										{/* Blog Tags Post List */}
									</div>
									{/* Single Sidebar */}
									{/* Single Sidebar */}
									<div className="rounded-[10px] border border-[#EAEDF0] p-8">
										<div className="relative mb-[30px] inline-block pb-[10px] text-lg font-semibold after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-full after:bg-black">
											Subscribe
										</div>
										<p className="mb-3">
											Subscribe to our newsletter and get the latest news
											updates lifetime
										</p>
										<form action="#" method="post" className="flex flex-col">
											<input
												type="email"
												name="sidebar-newsletter"
												id="sidebar-newsletter"
												placeholder="Enter your email address"
												className="h-[60px] w-full rounded-[50px] border border-colorCodGray bg-transparent px-10 py-[15px] text-lg outline-none transition-all placeholder:text-black focus:border-colorOrangyRed"
												required=""
											/>
											<button
												type="submit"
												className="button mt-5 block rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white"
											>
												Subscribe Now
											</button>
										</form>
									</div>
									{/* Single Sidebar */}
								</aside>
								{/* Blog Aside */}
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</div>
				{/*...::: Blog Section End :::... */}
			</main>
			<Footer_01/>
		</>
	);
}

export default BlogDetails;
