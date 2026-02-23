import Footer_01 from "@/components/footer/Footer_01";
import Header_01 from "@/components/header/Header_01";
import Image from "next/image";
import Link from "next/link";

function signup() {
	return (
		<>
			<Header_01 />
			<main className="main-wrapper relative overflow-hidden">
				{/*...::: Signup Section Start :::... */}
				<section id="signup-section">
					{/* Section Spacer */}
					<div className="py-40 pt-36 xl:pb-[200px] xl:pt-[180px]">
						{/* Section Container */}
						<div className="global-container">
							<div className="mx-auto max-w-[910px] text-center">
								<h1 className="mb-[50px]">Create Account</h1>
								<div className="block rounded-lg bg-white px-[30px] py-[50px] text-left shadow-[0_4px_60px_0_rgba(0,0,0,0.1)] sm:px-10">
									{/* Sign Up Form */}
									<form
										action="#"
										method="post"
										className="flex flex-col gap-y-5"
									>
										{/* Form Group */}
										<div className="grid grid-cols-1 gap-6">
											{/* Form Single Input */}
											<div className="flex flex-col gap-y-[10px]">
												<label
													htmlFor="signup-name"
													className="text-lg font-bold leading-[1.6]"
												>
													Enter your name
												</label>
												<input
													type="text"
													name="signup-name"
													id="signup-name"
													placeholder="Adam Smith"
													className="rounded-[10px] border border-gray-300 bg-white px-6 py-[18px] font-bold text-black outline-none transition-all placeholder:text-slate-500 focus:border-colorOrangyRed"
													required=""
												/>
											</div>
											{/* Form Single Input */}
											{/* Form Single Input */}
											<div className="flex flex-col gap-y-[10px]">
												<label
													htmlFor="signup-email"
													className="text-lg font-bold leading-[1.6]"
												>
													Email address
												</label>
												<input
													type="email"
													name="signup-email"
													id="signup-email"
													placeholder="example@gmail.com"
													className="rounded-[10px] border border-gray-300 bg-white px-6 py-[18px] font-bold text-black outline-none transition-all placeholder:text-slate-500 focus:border-colorOrangyRed"
													required=""
												/>
											</div>
											{/* Form Single Input */}
											{/* Form Single Input */}
											<div className="flex flex-col gap-y-[10px]">
												<label
													htmlFor="signup-password"
													className="text-lg font-bold leading-[1.6]"
												>
													Enter Password
												</label>
												<input
													type="password"
													name="signup-password"
													id="signup-password"
													placeholder="............"
													className="rounded-[10px] border border-gray-300 bg-white px-6 py-[18px] font-bold text-black outline-none transition-all placeholder:text-slate-500 focus:border-colorOrangyRed"
													required=""
												/>
											</div>
											{/* Form Single Input */}
											{/* Form Single Input */}
											<div className="flex gap-x-8 gap-y-[10px]">
												<input
													type="checkbox"
													className="relative appearance-none after:absolute after:left-0 after:top-[6px] after:h-4 after:w-4 after:rounded-[3px] after:border after:border-[#7F8995] after:bg-white after:text-white after:transition-all after:delay-300 checked:after:border-colorOrangyRed checked:after:bg-colorOrangyRed checked:after:bg-[url(/assets/img_placeholder/th-1/icon-white-checkmark-filled.svg)]"
													name="signup-check"
													id="signup-check"
													required=""
												/>
												<label
													htmlFor="signup-check"
													className="text-base leading-[1.6]"
												>
													I have read and accept the
													<Link
														href="#"
														className="font-bold hover:text-colorOrangyRed"
													>
														Terms &amp; Conditions
													</Link>
													and
													<Link
														href="#"
														className="font-bold hover:text-colorOrangyRed"
													>
														Privacy Policy
													</Link>
												</label>
											</div>
											{/* Form Single Input */}
										</div>
										<button
											type="submit"
											className="button mt-7 block rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white"
										>
											Create account
										</button>
										{/* Form Group */}
									</form>
									{/* Sign Up Form */}
									<div className="relative z-[1] mb-14 mt-9 text-center font-bold before:absolute before:left-0 before:top-1/2 before:-z-[1] before:h-[1px] before:w-full before:-translate-y-1/2 before:bg-[#EAEDF0]">
										<span className="inline-block bg-white px-6">Or</span>
									</div>
									{/* API Signup */}
									<div className="flex flex-col gap-y-6">
										{/* Google API Signup Button */}
										<button
											type="button"
											className="button flex w-full justify-center gap-x-4 rounded-[50px] border-2 border-[#EAEDF0] bg-white py-4 hover:bg-slate-200"
										>
											<span className="hidden h-6 w-6 sm:inline-block">
												<Image
													src="/assets/img_placeholder/th-1/flat-color-icons-google.svg"
													alt="flat-color-icons-google"
													width={24}
													height={24}
												/>
											</span>
											Signup with Google
										</button>
										{/* Google API Signup Button */}
										{/* Facebook API Signup Button */}
										<button
											type="button"
											className="button flex w-full justify-center gap-x-4 rounded-[50px] border-2 border-[#EAEDF0] bg-white py-4 hover:bg-slate-200"
										>
											<span className="hidden h-6 w-6 sm:inline-block">
												<Image
													src="/assets/img_placeholder/th-1/flat-color-icon-facebook.svg"
													alt="flat-color-icon-facebook"
													width={24}
													height={24}
												/>
											</span>
											Signup with Facebook
										</button>
										{/* Facebook API Signup Button */}
									</div>
									{/* API Signup */}
									<div className="mt-10 text-center">
										Already have an account?
										<Link
											href="/login"
											className="text-base font-semibold hover:text-colorOrangyRed"
										>
											Log in here
										</Link>
									</div>
								</div>
							</div>
						</div>
						{/* Section Container */}
					</div>
					{/* Section Spacer */}
				</section>
				{/*...::: Signup Section End :::... */}
			</main>
			<Footer_01 />
		</>
	);
}

export default signup;
