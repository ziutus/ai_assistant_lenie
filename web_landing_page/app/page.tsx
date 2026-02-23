'use client';
import Image from 'next/image';
import Link from 'next/link';
import { Autoplay } from 'swiper/modules';
import { Swiper, SwiperSlide } from 'swiper/react';
import useAccordion from '@/components/hooks/useAccordion';
import useTabs from '@/components/hooks/useTabs';
import Header_01 from '@/components/header/Header_01';
import Footer_01 from '@/components/footer/Footer_01';

function Home() {
  const [activeIndex, handleAccordion] = useAccordion(0);

  const [activeTab, handleTab] = useTabs();

  return (
    <div className='page-wrapper relative z-[1] bg-white'>
      {/*...::: Header Start :::... */}
      <Header_01 />
      {/*...::: Header End :::... */}
      <main className='main-wrapper relative overflow-hidden'>
        {/*...::: Hero Section Start :::... */}
        <section id='section-hero'>
          <div className='relative z-[1] overflow-hidden rounded-bl-[30px] rounded-br-[30px] bg-colorLinenRuffle pb-20 pt-28 lg:rounded-bl-[50px] lg:rounded-br-[50px] lg:pb-24 lg:pt-32 xl:pt-40 xxl:pb-[133px] xxl:pt-[195px]'>
            <div className='global-container'>
              <div className='mb-14 flex flex-col items-center text-center lg:mb-20'>
                <h1 className='jos slide-from-bottom mb-6 max-w-[510px] lg:max-w-[768px] xl:max-w-[1076px]'>
                  Master knowledge with AI-powered insights
                </h1>
                <p className='jos slide-from-bottom mb-11 max-w-[700px] text-lg font-semibold sm:text-xl xl:max-w-[980px]'>
                  Organize and analyze your notes, articles, and video transcripts with advanced AI. Our solution helps
                  with translation, summarization, and content search, providing quick and easy access to the
                  information you need.
                </p>
                <div
                    className='jos flex flex-wrap justify-center gap-6'
                    data-jos_animation='fade'
                >
                  <Link
                      href='https://app2.lenie-ai.eu/signup'
                      className='button rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white'
                  >
                    Get started for free *
                  </Link>
                  <Link
                      href='#'
                      className='button rounded-[50px] border-2 border-black bg-transparent py-4 text-black after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white'
                  >
                    Learn more
                  </Link>
                </div>
                <div className='flex justify-center'>
                  <p className='jos slide-from-bottom mb-11 max-w-[700px] text-lg font-semibold sm:text-xl xl:max-w-[980px] text-center mt-4'>
                    * A Application is in PoC (Prove on Concept phase). All users must be approved before can use the
                    application
                  </p>
                </div>
                </div>
                <div
                    className='jos hero-img overflow-hidden rounded-2xl bg-black'
                    data-jos_animation='zoom'
                >
                  <Image
                      src='/assets/screenshots/lenie_ai_welcome_1296_640.jpg'
                      alt='hero-dashboard'
                      width='1296'
                      height='640'
                      className='h-auto w-full'
                  />
                </div>


              </div>

            </div>
        </section>
        {/*...::: Hero Section End :::... */}

        {/*...::: Service Section Start :::... */}
        <section id='section-service'>
          {/* Section Spacer */}
          <div className='pb-20 pt-20 xl:pb-[150px] xl:pt-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mb-10 lg:mb-16 xl:mb-20'>
                <div className='md:max-w-sm lg:max-w-xl xl:max-w-[746px]'>
                  <h2>Core features that make it valuable</h2>
                </div>
              </div>
              {/* Section Content Block */}
              {/* Service List */}
              <ul className='jos grid grid-cols-1 gap-[2px] overflow-hidden rounded-[10px] border-2 border-black bg-black sm:grid-cols-2 lg:grid-cols-4'>
                {/* Service Item */}
                <li className='group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black'>
                  <div className='relative mb-9 h-[70px] w-[70px]'>
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-black-1.svg'
                      alt=''
                      width='70'
                      height='70'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-orange-1.svg'
                      alt='service-icon-orange-1'
                      width='70'
                      height='70'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </div>
                  <h3 className='mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]'>
                    <Link
                      href='/service-details'
                      className='hover:text-colorOrangyRed'
                    >
                      Multilingual Support
                    </Link>
                  </h3>

                  <p className='mb-12 duration-300 group-hover:text-white'>
                    Our AI-powered system efficiently manages and analyzes multilingual resources.
                  </p>

                  <Link
                    href='/service-details'
                    className='relative inline-block h-[30px] w-[30px] duration-300'
                  >
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-black.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-orange.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li className='group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black'>
                  <div className='relative mb-9 h-[70px] w-[70px]'>
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-black-2.svg'
                      alt='service-icon-black-2'
                      width='70'
                      height='70'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-orange-2.svg'
                      alt='service-icon-orange-1'
                      width='70'
                      height='70'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </div>

                  <h3 className='mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]'>
                    <Link
                      href='/service-details'
                      className='hover:text-colorOrangyRed'
                    >
                      Advanced Search Capabilities
                    </Link>
                  </h3>

                  <p className='mb-12 duration-300 group-hover:text-white'>
                    Utilizes AI-powered similarity search to quickly locate and retrieve pertinent information from extensive datasets
                  </p>

                  <Link
                    href='/service-details'
                    className='relative inline-block h-[30px] w-[30px] duration-300'
                  >
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-black.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-orange.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </Link>
                  {/* Features Item */}
                  {/* Features Item */}
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li className='group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black'>
                  <div className='relative mb-9 h-[70px] w-[70px]'>
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-black-3.svg'
                      alt='service-icon-black-3'
                      width='70'
                      height='70'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-orange-3.svg'
                      alt='service-icon-orange-3'
                      width='70'
                      height='70'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </div>
                  <h3 className='mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]'>
                    <Link
                      href='/service-details'
                      className='hover:text-colorOrangyRed'
                    >
                      Web-Based Access
                    </Link>
                  </h3>

                  <p className='mb-12 duration-300 group-hover:text-white'>
                    This is an excellent option for people & small businesses
                    who are starting out.
                  </p>

                  <Link
                    href='/service-details'
                    className='relative inline-block h-[30px] w-[30px] duration-300'
                  >
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-black.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-orange.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li className='group bg-white p-[30px] transition-all duration-300 ease-in-out hover:bg-black'>
                  <div className='relative mb-9 h-[70px] w-[70px]'>
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-black-4.svg'
                      alt='service-icon-black-4'
                      width='70'
                      height='70'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/service-icon-orange-4.svg'
                      alt='service-icon-orange-4'
                      width='70'
                      height='70'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
                    />
                  </div>
                  <h3 className='mb-4 block text-xl leading-tight -tracking-[0.5px] group-hover:text-white xl:text-2xl xxl:text-[28px]'>
                    <Link
                      href='/service-details'
                      className='hover:text-colorOrangyRed'
                    >
                      Integration with Your System
                    </Link>
                  </h3>

                  <p className='mb-12 duration-300 group-hover:text-white'>
                    Seamlessly integrate with our system using secure API keys, enabling you to extend your application's functionality and automate data workflows with confidence and ease.
                  </p>

                  <Link
                    href='/service-details'
                    className='relative inline-block h-[30px] w-[30px] duration-300'
                  >
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-black.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                    />
                    <Image
                      src='/assets/img_placeholder/th-1/arrow-right-orange.svg'
                      alt='arrow-right-black'
                      width='30'
                      height='30'
                      className='absolute left-0 top-0 h-full w-full opacity-0 transition-all duration-300 ease-linear group-hover:opacity-100'
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

        {/*...::: Content Section Start_1 :::... */}
        <section id='content-section-1'>
          {/* Section Spacer */}
          <div className='pb-20 xl:pb-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='grid grid-cols-1 items-center gap-12 md:grid-cols-2 lg:gap-20 xl:gap-28 xxl:gap-32'>
                {/* Content Left Block */}
                <div
                  className='jos order-2 overflow-hidden rounded-md md:order-1'
                  data-jos_animation='fade-left'
                >
                  <Image
                    src='/assets/screenshots/lenie_ai_chat_box_526_450.jpg'
                    alt='content-image-1'
                    width='526'
                    height='450'
                    className='h-auto w-full'
                  />
                </div>
                {/* Content Left Block */}
                {/* Content Right Block */}
                <div
                  className='jos order-1 md:order-2'
                  data-jos_animation='fade-right'
                >
                  {/* Section Content Block */}
                  <div className='mb-6'>
                    <h2>Efficient Data Management</h2>
                  </div>
                  {/* Section Content Block */}
                  <div className='text-lg leading-[1.4] lg:text-[21px]'>
                    <p className='mb-7 last:mb-0'>
                      This AI-powered system streamlines data handling by swiftly retrieving, organizing, and analyzing information, helping businesses save time and resources.
                    </p>
                    <p className='mb-7 last:mb-0'>
                      The quality of our system’s outputs is influenced by the depth of the data it analyzes and the sophistication of its AI, leading to more precise and insightful results.
                    </p>
                  </div>
                </div>
                {/* Content Right Block */}
              </div>
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Content Section End_1 :::... */}

        {/*...::: Content Section Start_2 :::... */}
        <section id='content-section-2'>
          {/* Section Spacer */}
          <div className='pb-20 xl:pb-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='grid grid-cols-1 items-center gap-12 md:grid-cols-2 lg:gap-20 xl:grid-cols-[minmax(0,_1.2fr)_1fr] xl:gap-28 xxl:gap-32'>
                {/* Content Left Block */}
                <div
                  className='jos order-2 overflow-hidden rounded-md'
                  data-jos_animation='fade-left'
                >
                  <Image
                    src='/assets/screenshots/lenie_ai_generate_voice_526_450.jpg'
                    alt='content-image-2'
                    width='526'
                    height='450'
                    className='h-auto w-full'
                  />
                </div>
                {/* Content Left Block */}
                {/* Content Right Block */}
                <div className='jos order-1' data-jos_animation='fade-right'>
                  {/* Section Content Block */}
                  <div className='mb-6'>
                    <h2>Always Provide the Most Relevant Insights</h2>
                  </div>
                  {/* Section Content Block */}
                  <div className='text-lg leading-[1.4] lg:text-[21px]'>
                    <p className='mb-7 last:mb-0'>
                      Our AI-powered system is designed to deliver accurate and relevant insights based on the data it processes and the algorithms it utilizes, ensuring high-quality analyses and summaries.
                    </p>
                    <ul className='flex flex-col gap-y-5 font-dmSans text-xl leading-tight tracking-tighter text-black lg:mt-12 lg:text-[28px]'>
                      <li className='flex items-start gap-x-3'>
                        <div className='mt-[2.5px] h-[30px] w-[30px]'>
                          <Image
                            src='/assets/img_placeholder/th-1/check-circle.svg'
                            alt='check-circle'
                            width='30'
                            height='30'
                            className='h-full w-full'
                          />
                        </div>
                        Retrieve information instantly from various sources
                      </li>
                      <li className='flex items-start gap-x-3'>
                        <div className='mt-[2.5px] h-[30px] w-[30px]'>
                          <Image
                            src='/assets/img_placeholder/th-1/check-circle.svg'
                            alt='check-circle'
                            width='30'
                            height='30'
                            className='h-full w-full'
                          />
                        </div>
                        Analyze and summarize multiple pieces of content simultaneously
                      </li>
                      <li className='flex items-start gap-x-3'>
                        <div className='mt-[2.5px] h-[30px] w-[30px]'>
                          <Image
                            src='/assets/img_placeholder/th-1/check-circle.svg'
                            alt='check-circle'
                            width='30'
                            height='30'
                            className='h-full w-full'
                          />
                        </div>
                        Time savings translate to cost savings
                      </li>
                    </ul>
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

        {/*...::: Funfact Section Start :::... */}
        <section id='funfact-section'>
          <div className='mx-auto max-w-[1500px] px-5'>
            <div className='jos grid grid-cols-1 overflow-hidden rounded-[30px] bg-black lg:rounded-[50px] xl:grid-cols-[minmax(400px,_1fr)_1.5fr] xxl:grid-cols-[1fr_minmax(800px,_1fr)]'>
              {/* Funfact Left Block */}
              <div className='relative overflow-hidden rounded-[30px] lg:rounded-[50px]'>
                <Image
                  src='/assets/screenshots/lenie_ai_generate_image_700_784.jpg'
                  alt='funfact-image'
                  width='721'
                  height='784'
                  className='h-80 w-full object-cover object-center lg:h-[35rem] xl:h-full'
                />
                {/* Video Play Button */}
                <Link
                  data-fslightbox='gallery'
                  rel='noopener noreferrer'
                  href='https://www.youtube.com/watch?v=3nQNiWdeH2Q'
                  className='absolute left-1/2 top-1/2 z-[1] -translate-x-1/2 -translate-y-1/2'
                >
                  <div className='relative flex h-[120px] w-[120px] items-center justify-center rounded-full border-[3px] border-black text-lg font-bold backdrop-blur-[2px] transition-all duration-300 hover:bg-colorOrangyRed hover:text-white'>
                    Play
                    <div className='absolute -z-[1] h-[110%] w-[110%] animate-[ping_1.5s_ease-in-out_infinite] rounded-full bg-gray-600 opacity-30'></div>
                  </div>
                </Link>
                {/* Video Play Button */}
              </div>
              {/* Funfacct Left Block */}

              {/* Funfact Right Block */}
              <div className='self-center px-6 py-16 sm:py-20 md:px-16 xl:px-10 xl:py-24 xxl:py-32 xxl:pl-16 xxl:pr-28'>
                {/* Section Content Block */}
                <div className='mb-8 lg:mb-16 xl:mb-6'>
                  <h2 className='text-white'>
                    AI-powered that streamline tasks
                  </h2>
                </div>
                {/* Section Content Block */}
                <div className='text-left text-lg leading-[1.4] text-white lg:text-[21px]'>
                  <p className='mb-7 last:mb-0'>
                    As your business grows or your AI SaaS needs change, you can
                    easily adjust your subscription level to match those needs.
                    This flexibility ensures that AI remains an asset.
                  </p>
                </div>
                {/* Horizontal Separator */}
                <div className='my-14 h-[1px] w-full bg-colorCodGray'></div>
                {/* Counter Scroll */}
                <ul className='flex flex-col justify-center gap-x-11 gap-y-8 text-center sm:flex-row md:text-left xl:justify-normal xl:text-left xxl:gap-x-20'>
                  {/* Counter Items */}
                  <li>
                    <h3
                      className='text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-7xl xxl:text-[120px]'
                      data-module='countup'
                    >
                      <span className='start-number' data-countup-number='92'>
                        92
                      </span>
                      %
                    </h3>
                    <span className='block text-lg font-normal text-white lg:text-[21px]'>
                      Users staying with the service
                    </span>
                  </li>
                  {/* Counter Items */}
                  {/* Counter Items */}
                  <li>
                    <h3
                      className='text-5xl text-colorOrangyRed md:text-6xl lg:text-7xl xl:text-7xl xxl:text-[120px]'
                      data-module='countup'
                    >
                      <span className='start-number' data-countup-number='75'>
                        75
                      </span>
                      %
                    </h3>
                    <span className='block text-lg font-normal text-white lg:text-[21px]'>
                      Pro Paid version users
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

        {/*...::: Pricing Section Start :::... */}
        <section className='pricing-section'>
          {/* Section Spacer */}
          <div className='pb-20 pt-20 xl:pb-[150px] xl:pt-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mb-10 text-center lg:mb-12'>
                <div className='mx-auto md:max-w-xs lg:max-w-xl xl:max-w-[746px]'>
                  <h2>Cost-effectively manage your notes</h2>
                </div>
              </div>
              {/* Section Content Block */}
              {/* Pricing Block */}
              <div className='container mx-auto'>
                {/* Tab buttons */}
                <div
                  className='jos flex justify-center'
                  data-jos_animation='fade'
                >
                  <div className='inline-flex space-x-4 rounded-[50px] border-2 border-black font-semibold'>
                    <button
                      className={`tab-button price-button ${
                        activeTab === 0 ? 'active' : ''
                      }`}
                      onClick={() => handleTab(0)}
                      data-tab='monthly'
                    >
                      Monthly
                    </button>
                    <button
                      className={`tab-button price-button ${
                        activeTab === 1 ? 'active' : ''
                      }`}
                      onClick={() => handleTab(1)}
                      data-tab='annually'
                    >
                      Annually
                    </button>
                  </div>
                </div>

                {/* Pricing Block */}
                <div className='mt-12 lg:mt-16 xl:mt-20'>
                  {/* Price List */}
                  {activeTab === 0 && (
                    <ul
                      id='monthly'
                      className='tab-content grid grid-cols-1 gap-6 md:grid-cols-2 xxl:grid-cols-3'
                    >
                      {/* Price Item */}
                      <li
                        className='jos group flex flex-col rounded-[10px] bg-colorLinenRuffle p-10 transition-all duration-300 ease-linear hover:bg-black'
                        data-jos_animation='flip'
                        data-jos_delay='0'
                      >
                        <h3 className='font-dmSans text-[28px] font-bold leading-[1.28] tracking-tighter text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Beginner
                        </h3>
                        <span className='text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Up to 500 entries
                        </span>

                        <div className='my-5 h-[1px] w-full bg-[#DBD6CF]'></div>
                        <h4 className='mb-4 font-dmSans text-5xl font-bold leading-none text-black transition-all duration-300 ease-linear group-hover:text-white md:text-6xl lg:text-7xl xl:text-[80px]'>
                          $1
                          <span className='text-lg font-semibold'>
                            /Per month
                          </span>
                        </h4>
                        <p className='mb-10 text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          This is an excellent option for people & small
                          businesses who are starting out.
                        </p>
                        <Link
                          href='/pricing'
                          className='button mt-auto block rounded-[50px] border-2 border-black bg-transparent py-4 text-center text-black transition-all duration-300 ease-linear after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-black group-hover:border-colorOrangyRed group-hover:text-white'
                        >
                          Choose the plan
                        </Link>
                      </li>
                      {/* Price Item */}
                      {/* Price Item */}
                      <li
                        className='jos group flex flex-col rounded-[10px] bg-colorLinenRuffle p-10 transition-all duration-300 ease-linear hover:bg-black'
                        data-jos_animation='flip'
                        data-jos_delay='0'
                      >
                        <h3 className='font-dmSans text-[28px] font-bold leading-[1.28] tracking-tighter text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Starter
                        </h3>
                        <span className='text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Up to 5000 entries
                        </span>

                        <div className='my-5 h-[1px] w-full bg-[#DBD6CF]'></div>
                        <h4 className='mb-4 font-dmSans text-5xl font-bold leading-none text-black transition-all duration-300 ease-linear group-hover:text-white md:text-6xl lg:text-7xl xl:text-[80px]'>
                          $10
                          <span className='text-lg font-semibold'>
                            /Per month
                          </span>
                        </h4>
                        <p className='mb-10 text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          This plan is suitable for professional blogs.
                        </p>
                        <Link
                          href='/pricing'
                          className='button mt-auto block rounded-[50px] border-2 border-black bg-transparent py-4 text-center text-black transition-all duration-300 ease-linear after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-black group-hover:border-colorOrangyRed group-hover:text-white'
                        >
                          Choose the plan
                        </Link>
                      </li>
                      {/* Price Item */}
                      {/* Price Item */}
                      <li
                        className='jos group flex flex-col rounded-[10px] bg-colorLinenRuffle p-10 transition-all duration-300 ease-linear hover:bg-black'
                        data-jos_animation='flip'
                        data-jos_delay='0'
                      >
                        <h3 className='font-dmSans text-[28px] font-bold leading-[1.28] tracking-tighter text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Pro
                        </h3>
                        <span className='text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Up to 20000 entries
                        </span>

                        <div className='my-5 h-[1px] w-full bg-[#DBD6CF]'></div>
                        <h4 className='mb-4 font-dmSans text-5xl font-bold leading-none text-black transition-all duration-300 ease-linear group-hover:text-white md:text-6xl lg:text-7xl xl:text-[80px]'>
                          $25
                          <span className='text-lg font-semibold'>
                            /Per month
                          </span>
                        </h4>
                        <p className='mb-10 text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Ideal for handling complicated projects.
                        </p>
                        <Link
                          href='/pricing'
                          className='button mt-auto block rounded-[50px] border-2 border-black bg-transparent py-4 text-center text-black transition-all duration-300 ease-linear after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-black group-hover:border-colorOrangyRed group-hover:text-white'
                        >
                          Choose the plan
                        </Link>
                      </li>
                      {/* Price Item */}
                    </ul>
                  )}
                  {/* Price List */}
                  {/* Price List */}
                  {activeTab === 1 && (
                    <ul
                      id='annually'
                      className='tab-content grid grid-cols-1 gap-6 md:grid-cols-2 xxl:grid-cols-3'
                    >
                      {/* Price Item */}
                      <li
                        className='jos group flex flex-col rounded-[10px] bg-colorLinenRuffle p-10 transition-all duration-300 ease-linear hover:bg-black'
                        data-jos_animation='flip'
                        data-jos_delay='0'
                      >
                        <h3 className='font-dmSans text-[28px] font-bold leading-[1.28] tracking-tighter text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Beginner
                        </h3>
                        <span className='text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Up to 500 entries
                        </span>

                        <div className='my-5 h-[1px] w-full bg-[#DBD6CF]'></div>
                        <h4 className='mb-4 font-dmSans text-5xl font-bold leading-none text-black transition-all duration-300 ease-linear group-hover:text-white md:text-6xl lg:text-7xl xl:text-[80px]'>
                          $9
                          <span className='text-lg font-semibold'>
                            /Per year
                          </span>
                        </h4>
                        <p className='mb-10 text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          This is an excellent option for people & small
                          businesses who are starting out.
                        </p>
                        <Link
                          href='/pricing'
                          className='button mt-auto block rounded-[50px] border-2 border-black bg-transparent py-4 text-center text-black transition-all duration-300 ease-linear after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-black group-hover:border-colorOrangyRed group-hover:text-white'
                        >
                          Choose the plan
                        </Link>
                      </li>
                      {/* Price Item */}
                      {/* Price Item */}
                      <li
                        className='jos group flex flex-col rounded-[10px] bg-colorLinenRuffle p-10 transition-all duration-300 ease-linear hover:bg-black'
                        data-jos_animation='flip'
                        data-jos_delay='0'
                      >
                        <h3 className='font-dmSans text-[28px] font-bold leading-[1.28] tracking-tighter text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Starter
                        </h3>
                        <span className='text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Up to 5000 entries
                        </span>

                        <div className='my-5 h-[1px] w-full bg-[#DBD6CF]'></div>
                        <h4 className='mb-4 font-dmSans text-5xl font-bold leading-none text-black transition-all duration-300 ease-linear group-hover:text-white md:text-6xl lg:text-7xl xl:text-[80px]'>
                          $100
                          <span className='text-lg font-semibold'>
                            /Per year
                          </span>
                        </h4>
                        <p className='mb-10 text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          This plan is suitable for professional blogs.
                        </p>
                        <Link
                          href='/pricing'
                          className='button mt-auto block rounded-[50px] border-2 border-black bg-transparent py-4 text-center text-black transition-all duration-300 ease-linear after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-black group-hover:border-colorOrangyRed group-hover:text-white'
                        >
                          Choose the plan
                        </Link>
                      </li>
                      {/* Price Item */}
                      {/* Price Item */}
                      <li
                        className='jos group flex flex-col rounded-[10px] bg-colorLinenRuffle p-10 transition-all duration-300 ease-linear hover:bg-black'
                        data-jos_animation='flip'
                        data-jos_delay='0'
                      >
                        <h3 className='font-dmSans text-[28px] font-bold leading-[1.28] tracking-tighter text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Pro
                        </h3>
                        <span className='text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Up to 20000 entries
                        </span>

                        <div className='my-5 h-[1px] w-full bg-[#DBD6CF]'></div>
                        <h4 className='mb-4 font-dmSans text-5xl font-bold leading-none text-black transition-all duration-300 ease-linear group-hover:text-white md:text-6xl lg:text-7xl xl:text-[80px]'>
                          $250
                          <span className='text-lg font-semibold leading-none'>
                            /Per year
                          </span>
                        </h4>
                        <p className='mb-10 text-lg text-black transition-all duration-300 ease-linear group-hover:text-white'>
                          Ideal for handling complicated projects
                          enterprise-level projects, and websites.
                        </p>
                        <Link
                          href='/pricing'
                          className='button mt-auto block rounded-[50px] border-2 border-black bg-transparent py-4 text-center text-black transition-all duration-300 ease-linear after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-black group-hover:border-colorOrangyRed group-hover:text-white'
                        >
                          Choose the plan
                        </Link>
                      </li>
                      {/* Price Item */}
                    </ul>
                  )}
                  {/* Price List */}
                </div>
                {/* Pricing Block */}
              </div>
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Pricing Section End :::... */}

        {/*...::: FAQ Section Start :::... */}
        <section className='faq-section'>
          {/* Section Spacer */}
          <div className='pb-20 xl:pb-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='grid grid-cols-1 gap-y-10 md:grid-cols-2'>
                {/* FAQ Left Block */}
                <div
                  className='jos flex flex-col'
                  data-jos_animation='fade-right'
                >
                  {/* Section Content Block */}
                  <div className='mb-6'>
                    <div className='mx-auto md:mx-0 md:max-w-none'>
                      <h2>Freely ask us for more information</h2>
                    </div>
                  </div>
                  {/* Section Content Block */}
                  <div className='text-lg leading-[1.4] lg:text-[21px]'>
                    <p className='mb-7 last:mb-0'>
                      Our AI SaaS solutions can be quickly deployed, enabling
                      users to start benefiting from AI capabilities without
                      lengthy setup and development times in fast-paced
                      industries.
                    </p>
                    <Link
                      href='/faq-1'
                      className='button mt-5 rounded-[50px] border-2 border-black bg-black py-4 text-white after:bg-colorOrangyRed hover:border-colorOrangyRed hover:text-white'
                    >
                      Ask you questions
                    </Link>
                  </div>
                </div>
                {/* FAQ Left Block */}

                {/* FAQ Right Block */}
                <div
                  className='jos md:ml-10 lg:ml-20 xl:ml-32'
                  data-jos_animation='fade-left'
                >
                  {/* Accordion*/}
                  <ul className='accordion'>
                    {/* Accordion items */}
                    <li
                      className={`accordion-item border-b-[1px] border-[#DBD6CF] pb-6 pt-6 first:pt-0 last:border-b-0 last:pb-0 ${
                        activeIndex === 0 ? 'active' : ''
                      }`}
                      onClick={() => handleAccordion(0)}
                    >
                      <div className='accordion-header flex items-center justify-between font-dmSans text-xl font-bold leading-[1.2] -tracking-[0.5px] text-black lg:text-[28px]'>
                        <p>How do I start AI SaaS?</p>
                        <div className='accordion-icon'>
                          <Image
                            src='/assets/img_placeholder/plus.svg'
                            width={24}
                            height={24}
                            alt='plus'
                          />
                        </div>
                      </div>
                      <div className='accordion-content text-[#2C2C2C]'>
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
                        activeIndex === 1 ? 'active' : ''
                      }`}
                      onClick={() => handleAccordion(1)}
                    >
                      <div className='accordion-header flex items-center justify-between font-dmSans text-xl font-bold leading-[1.2] -tracking-[0.5px] text-black lg:text-[28px]'>
                        <p>Can I customize AI SaaS solutions?</p>
                        <div className='accordion-icon'>
                          <Image
                            src='/assets/img_placeholder/plus.svg'
                            width={24}
                            height={24}
                            alt='plus'
                          />
                        </div>
                      </div>
                      <div className='accordion-content text-[#2C2C2C]'>
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
                        activeIndex === 2 ? 'active' : ''
                      }`}
                      onClick={() => handleAccordion(2)}
                    >
                      <div className='accordion-header flex items-center justify-between font-dmSans text-xl font-bold leading-[1.2] -tracking-[0.5px] text-black lg:text-[28px]'>
                        <p>How can AI benefit my business?</p>
                        <div className='accordion-icon'>
                          <Image
                            src='/assets/img_placeholder/plus.svg'
                            width={24}
                            height={24}
                            alt='plus'
                          />
                        </div>
                      </div>
                      <div className='accordion-content text-[#2C2C2C]'>
                        <p>
                          Go to the our official website and require users to
                          create an account. Youll need to provide some basic
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
        <section className='testimonial-section'>
          {/* Section Spacer */}
          <div className='bg-black pb-40 pt-20 xl:pb-[200px] xl:pt-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mb-10 text-center lg:mb-16 xl:mb-20'>
                <div className='mx-auto max-w-[300px] lg:max-w-[600px] xl:max-w-[680px]'>
                  <h2 className='text-white'>
                    Positive feedback from our users
                  </h2>
                </div>
              </div>
              {/* Section Content Block */}

              {/* Testimonial List */}
              <div className='grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3'>
                {/* Testimonial Item */}
                <div
                  className='jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'
                  data-jos_animation='fade-left'
                  data-jos_delay='0.1'
                >
                  <div className='block'>
                    <Image
                      src='/assets/img_placeholder/th-1/rating.svg'
                      alt='rating'
                      width='146'
                      height='25'
                    />
                  </div>
                  <p>
                    I've been using this AI-powered system for managing and analyzing data over the past year. It’s intuitive and user-friendly, making it easy to explore and organize information. The support team is responsive and thorough. Great job!
                  </p>
                  <div className='flex items-center gap-x-4'>
                    <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                      <Image
                        src='/assets/img_placeholder/th-1/testimonial-img-1.jpg'
                        alt='testimonial-img'
                        width='60'
                        height='60'
                        className='h-full w-full object-cover object-center'
                      />
                    </div>
                    <div className='flex flex-col gap-y-1'>
                      <span className='block text-lg font-semibold leading-[1.6]'>
                        Max Weber
                      </span>
                      <span className='block text-sm font-light leading-[1.4]'>
                        Professional blog writer
                      </span>
                    </div>
                  </div>
                </div>
                {/* Testimonial Item */}
                {/* Testimonial Item */}
                <div
                  className='jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'
                  data-jos_animation='fade-left'
                  data-jos_delay='0.2'
                >
                  <div className='block'>
                    <Image
                      src='/assets/img_placeholder/th-1/rating.svg'
                      alt='rating'
                      width='146'
                      height='25'
                    />
                  </div>
                  <p>
                    It answers immediately, and we ve seen a significant
                    reduction in response time. I love it!
                  </p>
                  <div className='flex items-center gap-x-4'>
                    <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                      <Image
                        src='/assets/img_placeholder/th-1/testimonial-img-2.jpg'
                        alt='testimonial-img'
                        width='60'
                        height='60'
                        className='h-full w-full object-cover object-center'
                      />
                    </div>
                    <div className='flex flex-col gap-y-1'>
                      <span className='block text-lg font-semibold leading-[1.6]'>
                        Douglas Smith
                      </span>
                      <span className='block text-sm font-light leading-[1.4]'>journalist
                      </span>
                    </div>
                  </div>
                </div>
                {/* Testimonial Item */}
                {/* Testimonial Item */}
                <div
                  className='jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'
                  data-jos_animation='fade-left'
                  data-jos_delay='0.3'
                >
                  <div className='block'>
                    <Image
                      src='/assets/img_placeholder/th-1/rating.svg'
                      alt='rating'
                      width='146'
                      height='25'
                    />
                  </div>
                  <p>
                    It is accurate, fast and supports multiple languages
                    support. It is a must for any international business
                    success.
                  </p>
                  <div className='flex items-center gap-x-4'>
                    <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                      <Image
                        src='/assets/img_placeholder/th-1/testimonial-img-3.jpg'
                        alt='testimonial-img'
                        width='60'
                        height='60'
                        className='h-full w-full object-cover object-center'
                      />
                    </div>
                    <div className='flex flex-col gap-y-1'>
                      <span className='block text-lg font-semibold leading-[1.6]'>
                        Lara Craft
                      </span>
                      <span className='block text-sm font-light leading-[1.4]'>
                        instagram influencer
                      </span>
                    </div>
                  </div>
                </div>
                {/* Testimonial Item */}
                {/* Testimonial Item */}
                <div
                  className='jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'
                  data-jos_animation='fade-right'
                  data-jos_delay='0.1'
                >
                  <div className='block'>
                    <Image
                      src='/assets/img_placeholder/th-1/rating.svg'
                      alt='rating'
                      width='146'
                      height='25'
                    />
                  </div>
                  <p>
                    Security is a top concern for us, and Lenie-AI SAAS takes it
                    seriously. It s a reassuring layer of protection for our
                    organization.
                  </p>
                  <div className='flex items-center gap-x-4'>
                    <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                      <Image
                        src='/assets/img_placeholder/th-1/testimonial-img-4.jpg'
                        alt='testimonial-img'
                        width='60'
                        height='60'
                        className='h-full w-full object-cover object-center'
                      />
                    </div>
                    <div className='flex flex-col gap-y-1'>
                      <span className='block text-lg font-semibold leading-[1.6]'>
                        Jack Fayol
                      </span>
                      <span className='block text-sm font-light leading-[1.4]'>
                        Hacker
                      </span>
                    </div>
                  </div>
                </div>
                {/* Testimonial Item */}
                {/* Testimonial Item */}
                <div
                  className='jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'
                  data-jos_animation='fade-right'
                  data-jos_delay='0.2'
                >
                  <div className='block'>
                    <Image
                      src='/assets/img_placeholder/th-1/rating.svg'
                      alt='rating'
                      width='146'
                      height='25'
                    />
                  </div>
                  <p>
                    We were concerned about integrating their APIs were well
                    documented, and their support team was super cool.
                  </p>
                  <div className='flex items-center gap-x-4'>
                    <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                      <Image
                        src='/assets/img_placeholder/th-1/testimonial-img-5.jpg'
                        alt='testimonial-img'
                        width='60'
                        height='60'
                        className='h-full w-full object-cover object-center'
                      />
                    </div>
                    <div className='flex flex-col gap-y-1'>
                      <span className='block text-lg font-semibold leading-[1.6]'>
                        Karen Lynn
                      </span>
                      <span className='block text-sm font-light leading-[1.4]'>
                        Software Engineer
                      </span>
                    </div>
                  </div>
                </div>
                {/* Testimonial Item */}
                {/* Testimonial Item */}
                <div
                  className='jos flex flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'
                  data-jos_animation='fade-right'
                  data-jos_delay='0.3'
                >
                  <div className='block'>
                    <Image
                      src='/assets/img_placeholder/th-1/rating.svg'
                      alt='rating'
                      width='146'
                      height='25'
                    />
                  </div>
                  <p>
                    The return on investment has exceeded our expectations. it s
                    an investment in the future of our business.
                  </p>
                  <div className='flex items-center gap-x-4'>
                    <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                      <Image
                        src='/assets/img_placeholder/th-1/testimonial-img-6.jpg'
                        alt='testimonial-img'
                        width='60'
                        height='60'
                        className='h-full w-full object-cover object-center'
                      />
                    </div>
                    <div className='flex flex-col gap-y-1'>
                      <span className='block text-lg font-semibold leading-[1.6]'>
                        Henry Ochi
                      </span>
                      <span className='block text-sm font-light leading-[1.4]'>
                        Private detective
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

        {/* Body Background Shape 1 */}
        <div className='orange-gradient-1 absolute -left-[15px] top-[61%] -z-[1] h-[400px] w-[400px] -rotate-[-9.022deg] rounded-[400px]'></div>

        {/* Body Background Shape 2 */}
        <div className='orange-gradient-2 absolute -left-[100px] top-[64%] -z-[1] h-[360px] w-[360px] -rotate-[-9.022deg] rounded-[360px]'></div>
      </main>
      {/*...::: Footer Start :::... */}
      <Footer_01 />
      {/*...::: Footer End :::... */}
    </div>
  );
}

export default Home;
