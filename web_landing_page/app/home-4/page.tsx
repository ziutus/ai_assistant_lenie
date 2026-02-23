'use client';
import { useState } from 'react';
import FsLightbox from 'fslightbox-react';
import useAccordion from '@/components/hooks/useAccordion';
import Image from 'next/image';
import Link from 'next/link';

const Home_4 = () => {
  // To open the lightbox change the value of the "toggler" prop.
  const [toggler, setToggler] = useState(false);
  const [activeIndex, handleAccordion] = useAccordion();
  const [activeIndexTwo, handleAccordionTwo] = useAccordion();

  return (
    <>
      <main className='main-wrapper relative overflow-hidden'>
        {/*...::: Hero Section Start :::... */}
        <section id='hero-section'>
          <div className='relative z-[1] overflow-hidden text-center text-white'>
            {/* Section Spacer */}
            <div className="bg-[url('/assets/img_placeholder/th-4/hero-bg.jpg')] bg-cover bg-no-repeat pb-20 pt-28 md:pb-[265px] md:pt-40 lg:pt-44 xl:pt-[224px]">
              {/* Section Container */}
              <div className='global-container'>
                <h1 className='jos mb-6 font-spaceGrotesk leading-none -tracking-[3px] text-white'>
                  Next-gen AI solutions for cybersecurity
                </h1>
                <div className='mx-auto max-w-[1090px]'>
                  <p className='leading-[1.33] lg:text-xl xl:text-2xl'>
                    AI solutions for cyber security play a critical role in
                    staying ahead of increasingly sophisticated cyber threats by
                    providing faster, more accurate threat detection and
                    response capabilities.
                  </p>
                </div>
                <form
                  action='#'
                  method='post'
                  className='jos mt-11 text-base font-bold'
                >
                  <div className='relative mx-auto h-[60px] max-w-[500px] overflow-hidden rounded'>
                    <input
                      type='email'
                      placeholder='Enter your email...'
                      className='h-full w-full bg-colorCodGray px-6 pr-[150px]'
                      required=''
                    />
                    <button
                      type='submit'
                      className='button absolute right-0 top-0 inline-block h-full rounded border-none bg-colorGreen py-0 text-black after:border-none after:bg-white'
                    >
                      Get Started
                    </button>
                  </div>
                </form>
                <div className='jos mt-4 flex items-center justify-center gap-x-[10px] text-center text-base'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-badge-check.svg'
                    alt='icon-green-badge-check.svg'
                    width={20}
                    height={20}
                    className='inline-block'
                  />
                  <p>
                    By signing up you agree to our
                    <Link
                      rel='noopener noreferrer'
                      href='http://www.example.com'
                      className='underline hover:text-colorGreen'
                    >
                      Terms &amp; Conditions.
                    </Link>
                  </p>
                </div>
              </div>
              {/* Section Container */}
            </div>
            {/* Background Gradient */}
            <div className='absolute left-1/2 top-[80%] -z-[1] h-[1280px] w-[1280px] -translate-x-1/2 rounded-full bg-gradient-to-t from-[#39FF14] to-[#37ff1467] blur-[250px]'></div>
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Hero Section End :::... */}
        {/*...::: Promo Section Start :::... */}
        <div id='promo-section'>
          <div className='relative z-[1] pt-20 md:-mt-[135px] md:pt-0'>
            {/* Section Container */}
            <div className='global-container'>
              <ul className='grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3'>
                <li
                  className='jos rounded-[10px] bg-[#121212] p-[30px] text-white'
                  data-jos_delay='0.1'
                >
                  <div className='mb-6 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-promo-1.svg'
                        alt='icon-black-promo'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Threat Detection
                    </div>
                  </div>
                  <p className='text-[21px] leading-[1.4]'>
                    AI can identify patterns &amp; improve the detection of
                    unknown threats.
                  </p>
                </li>
                <li
                  className='jos rounded-[10px] bg-[#121212] p-[30px] text-white'
                  data-jos_delay='0.2'
                >
                  <div className='mb-6 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-promo-2.svg'
                        alt='icon-black-promo'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      24/7 Monitoring
                    </div>
                  </div>
                  <p className='text-[21px] leading-[1.4]'>
                    Ensuring continuous protection against threats and working
                    hours.
                  </p>
                </li>
                <li
                  className='jos rounded-[10px] bg-[#121212] p-[30px] text-white'
                  data-jos_delay='0.3'
                >
                  <div className='mb-6 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-promo-3.svg'
                        alt='icon-black-promo'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Auto Response
                    </div>
                  </div>
                  <p className='text-[21px] leading-[1.4]'>
                    Automate routine security tasks and patch management
                    security.
                  </p>
                </li>
              </ul>
            </div>
            {/* Section Container */}
          </div>
        </div>
        {/*...::: Promo Section End :::... */}
        {/*...::: Content Section-1 Start :::... */}
        <section id='section-content-1'>
          {/* Section Spacer */}
          <div className='py-20 xl:py-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='grid items-center gap-10 md:grid-cols-[minmax(0,_1fr)_1.3fr] lg:gap-[60px] xl:gap-x-[94px]'>
                <div className='jos' data-jos_animation='fade-left'>
                  <div className='overflow-hidden rounded-[10px]'>
                    <Image
                      src='/assets/img_placeholder/th-4/content-img-1.jpg'
                      alt='content-img-2'
                      width={550}
                      height={550}
                      className='h-auto w-full'
                    />
                  </div>
                </div>
                <div className='jos' data-jos_animation='fade-right'>
                  {/* Section Content Block */}
                  <div className='mb-6'>
                    <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                      Securing networks, servers and data
                    </h2>
                  </div>
                  {/* Section Content Block */}
                  <div>
                    <p className='mb-8 text-lg leading-[1.42] last:mb-0 lg:text-[21px]'>
                      Large corporations &amp; businesses across industries use
                      our AI cybersecurity solutions to safeguard their
                      networks, servers, &amp; data from cyber threats.
                    </p>
                    <p className='mb-8 text-lg leading-[1.42] last:mb-0 lg:text-[21px]'>
                      Our cyber security platform supercharges your security
                      with AI-powered security tools. Turn mountains of data
                      into actionable insights and respond in real-time.
                    </p>
                    <Link
                      rel='noopener noreferrer'
                      href='https://www.example.com'
                      className='button inline-block h-full rounded border-none bg-colorGreen py-3 text-base text-black after:border-none after:bg-white'
                    >
                      Explore the Platform
                    </Link>
                  </div>
                </div>
              </div>
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Content Section-1 End :::... */}
        {/*...::: Content Section-2 Start :::... */}
        <section id='section-content-2'>
          {/* Section Spacer */}
          <div className='py-20 xl:py-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='grid items-center gap-10 md:grid-cols-[1.1fr_minmax(0,_1fr)] lg:gap-[60px] xl:gap-x-[110px]'>
                <div className='jos order-2' data-jos_animation='fade-left'>
                  <div className='overflow-hidden rounded-[10px]'>
                    <Image
                      src='/assets/img_placeholder/th-4/content-img-2.jpg'
                      alt='content-img-2'
                      width={550}
                      height={550}
                      className='h-auto w-full'
                    />
                  </div>
                </div>
                <div className='jos order-1' data-jos_animation='fade-right'>
                  {/* Section Content Block */}
                  <div className='mb-6'>
                    <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                      Industries protect their digital assets
                    </h2>
                  </div>
                  {/* Section Content Block */}
                  <div className=''>
                    <p className='mb-8 text-lg leading-[1.42] last:mb-0 lg:text-[21px]'>
                      Cybersecurity solutions are used by a wide range of all
                      types of organizations across various industries use to
                      protect their digital assets, networks, and sensitive
                      data.
                    </p>
                    <ul className='flex flex-col gap-y-5 font-spaceGrotesk text-xl leading-tight tracking-tighter lg:mt-12 lg:text-[28px]'>
                      <li className='flex items-start gap-x-3'>
                        <div className='mt-[2.5px] h-[30px] w-[30px]'>
                          <Image
                            src='/assets/img_placeholder/th-4/icon-green-badge-check.svg'
                            alt='check-circle'
                            width={30}
                            height={30}
                            className='h-full w-full'
                          />
                        </div>
                        AI cybersecurity to secure cloud platforms
                      </li>
                      <li className='flex items-start gap-x-3'>
                        <div className='mt-[2.5px] h-[30px] w-[30px]'>
                          <Image
                            src='/assets/img_placeholder/th-4/icon-green-badge-check.svg'
                            alt='check-circle'
                            width={30}
                            height={30}
                            className='h-full w-full'
                          />
                        </div>
                        Safeguard customer payment information
                      </li>
                      <li className='flex items-start gap-x-3'>
                        <div className='mt-[2.5px] h-[30px] w-[30px]'>
                          <Image
                            src='/assets/img_placeholder/th-4/icon-green-badge-check.svg'
                            alt='check-circle'
                            width={30}
                            height={30}
                            className='h-full w-full'
                          />
                        </div>
                        Secure digital assets and donor information
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Content Section-2 End :::... */}
        {/* Separator */}
        <div className='global-container overflow-hidden'>
          <div className='h-[1px] w-full bg-[#363636]' />
        </div>
        {/* Separator */}
        {/*...::: Service Section Start :::... */}
        <section id='service-section'>
          {/* Section Spacer */}
          <div className='pb-20 pt-20 xl:pb-[130px] xl:pt-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mx-auto mb-10 text-center md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[856px]'>
                <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                  Get all the tools to tackle cybersecurity together
                </h2>
              </div>
              {/* Section Content Block */}
              {/* Service List */}
              <ul className='grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3'>
                {/* Service Item */}
                <li
                  className='jos group rounded-[10px] bg-[#121212] p-[30px]'
                  data-jos_delay='0.1'
                >
                  <div className='mb-8 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-service-1.svg'
                        alt='icon-green-service'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Threat Detection
                    </div>
                  </div>
                  <p className='mb-7 text-[21px] leading-[1.4]'>
                    AI can identify patterns &amp; improve the detection of
                    unknown threats.
                  </p>
                  <Link
                    href='/service-details'
                    className='relative flex h-[30px] w-[30px] items-center justify-center overflow-hidden'
                  >
                    <Image
                      src='/assets/img_placeholder/th-4/icon-white-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='relative left-0 transition-all duration-300 group-hover:left-full'
                    />
                    <Image
                      src='/assets/img_placeholder/th-4/icon-green-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='absolute -left-full transition-all duration-300 group-hover:left-0'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li
                  className='jos group rounded-[10px] bg-[#121212] p-[30px]'
                  data-jos_delay='0.2'
                >
                  <div className='mb-8 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-service-2.svg'
                        alt='icon-green-service'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Phishing Detection
                    </div>
                  </div>
                  <p className='mb-7 text-[21px] leading-[1.4]'>
                    AI examines email content &amp; sender behavior to identify
                    phishing links.
                  </p>
                  <Link
                    href='/service-details'
                    className='relative flex h-[30px] w-[30px] items-center justify-center overflow-hidden'
                  >
                    <Image
                      src='/assets/img_placeholder/th-4/icon-white-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='relative left-0 transition-all duration-300 group-hover:left-full'
                    />
                    <Image
                      src='/assets/img_placeholder/th-4/icon-green-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='absolute -left-full transition-all duration-300 group-hover:left-0'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li
                  className='jos group rounded-[10px] bg-[#121212] p-[30px]'
                  data-jos_delay='0.3'
                >
                  <div className='mb-8 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-service-3.svg'
                        alt='icon-green-service'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Network Security
                    </div>
                  </div>
                  <p className='mb-7 text-[21px] leading-[1.4]'>
                    Network traffic attempts and can take automated actions to
                    block.
                  </p>
                  <Link
                    href='/service-details'
                    className='relative flex h-[30px] w-[30px] items-center justify-center overflow-hidden'
                  >
                    <Image
                      src='/assets/img_placeholder/th-4/icon-white-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='relative left-0 transition-all duration-300 group-hover:left-full'
                    />
                    <Image
                      src='/assets/img_placeholder/th-4/icon-green-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='absolute -left-full transition-all duration-300 group-hover:left-0'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li
                  className='jos group rounded-[10px] bg-[#121212] p-[30px]'
                  data-jos_delay='0.4'
                >
                  <div className='mb-8 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-service-4.svg'
                        alt='icon-green-service'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Encryption Tools
                    </div>
                  </div>
                  <p className='mb-7 text-[21px] leading-[1.4]'>
                    Encryption software and hardware protect data by converting
                    it.
                  </p>
                  <Link
                    href='/service-details'
                    className='relative flex h-[30px] w-[30px] items-center justify-center overflow-hidden'
                  >
                    <Image
                      src='/assets/img_placeholder/th-4/icon-white-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='relative left-0 transition-all duration-300 group-hover:left-full'
                    />
                    <Image
                      src='/assets/img_placeholder/th-4/icon-green-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='absolute -left-full transition-all duration-300 group-hover:left-0'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li
                  className='jos group rounded-[10px] bg-[#121212] p-[30px]'
                  data-jos_delay='0.5'
                >
                  <div className='mb-8 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-service-5.svg'
                        alt='icon-green-service'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Password Managers
                    </div>
                  </div>
                  <p className='mb-7 text-[21px] leading-[1.4]'>
                    Password managers help users create, store, &amp; unique
                    passwords.
                  </p>
                  <Link
                    href='/service-details'
                    className='relative flex h-[30px] w-[30px] items-center justify-center overflow-hidden'
                  >
                    <Image
                      src='/assets/img_placeholder/th-4/icon-white-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='relative left-0 transition-all duration-300 group-hover:left-full'
                    />
                    <Image
                      src='/assets/img_placeholder/th-4/icon-green-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='absolute -left-full transition-all duration-300 group-hover:left-0'
                    />
                  </Link>
                </li>
                {/* Service Item */}
                {/* Service Item */}
                <li
                  className='jos group rounded-[10px] bg-[#121212] p-[30px]'
                  data-jos_delay='0.6'
                >
                  <div className='mb-8 flex items-center gap-x-6'>
                    <div className='h-[50px] w-[50px]'>
                      <Image
                        src='/assets/img_placeholder/th-4/icon-green-service-6.svg'
                        alt='icon-green-service'
                        width={50}
                        height={50}
                        className='h-full w-auto'
                      />
                    </div>
                    <div className='flex-1 font-spaceGrotesk text-3xl leading-[1.33]'>
                      Secure Email
                    </div>
                  </div>
                  <p className='mb-7 text-[21px] leading-[1.4]'>
                    These solutions filter and block email-based threats emails,
                    spam.
                  </p>
                  <Link
                    href='/service-details'
                    className='relative flex h-[30px] w-[30px] items-center justify-center overflow-hidden'
                  >
                    <Image
                      src='/assets/img_placeholder/th-4/icon-white-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='relative left-0 transition-all duration-300 group-hover:left-full'
                    />
                    <Image
                      src='/assets/img_placeholder/th-4/icon-green-arrow-right.svg'
                      alt='icon-white-arrow-right'
                      width={30}
                      height={30}
                      className='absolute -left-full transition-all duration-300 group-hover:left-0'
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
        {/*...::: Text Slide Section Start :::... */}
        <div id='text-slide-section'>
          <div className='bg-colorGreen py-5'>
            <div className='horizontal-slide-from-left-to-right grid grid-flow-col whitespace-nowrap'>
              <div className='flex text-4xl font-bold uppercase leading-5 text-black'>
                #cybersecurity #hacking #tech #programming #coding
              </div>
              <div className='flex text-4xl font-bold uppercase leading-5 text-black'>
                #cybersecurity #hacking #tech #programming #coding
              </div>
              <div className='flex text-4xl font-bold uppercase leading-5 text-black'>
                #cybersecurity #hacking #tech #programming #coding
              </div>
            </div>
          </div>
        </div>
        {/*...::: Text Slide Section End :::... */}
        {/*...::: Content Section-3 Start :::... */}
        <section id='content-section-3'>
          {/* Section Spacer */}
          <div className='py-20 xl:pb-[150px] xl:pt-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mb-10 max-w-[480px] md:mb-16 lg:mb-20 lg:max-w-2xl xl:max-w-[800px]'>
                <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                  Defenses to stay ahead of all evolving all threats
                </h2>
              </div>
              {/* Section Content Block */}
              <div
                className='jso relative overflow-hidden rounded-[10px]'
                data-jos_animation='zoom'
              >
                <Image
                  src='/assets/img_placeholder/th-4/video-bg-image.jpg'
                  alt='video-bg-image'
                  width={1296}
                  height={600}
                  className='h-80 w-full object-cover object-center lg:h-[35rem] xl:h-full'
                />
                {/* Video Play Button */}
                <button className='absolute left-1/2 top-1/2 z-[1] -translate-x-1/2 -translate-y-1/2'>
                  <div
                    className='relative flex h-[120px] w-[120px] items-center justify-center rounded-full border-[3px] border-colorGreen bg-black text-lg font-bold backdrop-blur-[2px] transition-all duration-300'
                    onClick={() => setToggler(!toggler)}
                  >
                    Play
                    <div className='absolute -z-[1] h-[110%] w-[110%] animate-[ping_1.5s_ease-in-out_infinite] rounded-full bg-colorGreen opacity-30'></div>
                  </div>
                </button>
                {/* Video Play Button */}
              </div>
              <FsLightbox
                toggler={toggler}
                sources={['https://www.youtube.com/watch?v=3nQNiWdeH2Q']}
              />
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>

        {/*...::: Content Section-3 End :::... */}
        {/*...::: Content Section-4 Start :::... */}
        <section id='content-section-4'>
          {/* Section Spacer */}
          <div className='pb-20 xl:pb-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='grid items-center gap-12 lg:grid-cols-[minmax(0,_.75fr)_1fr] lg:gap-20 xl:gap-24'>
                {/* Process Accordion */}
                <ul
                  className='accordion tab-content flex flex-col gap-y-6'
                  id='process-accordian'
                >
                  {/* Accordion items */}
                  <li
                    className={`jos accordion-item rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                      activeIndex == 0 ? 'active' : ''
                    }`}
                    data-jos_delay='0.1'
                  >
                    <div
                      onClick={() => handleAccordion(0)}
                      className='accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[1px] lg:text-3xl'
                    >
                      <div className='mb-3 flex items-center gap-x-6'>
                        <Image
                          src='/assets/img_placeholder/th-4/icon-green-process-accordion-1.svg'
                          alt='icon-green-process-accordion'
                          width={36}
                          height={50}
                          className='h-[50px] w-auto'
                        />
                        <h5 className='font-spaceGrotesk text-white'>
                          Create a free account
                        </h5>
                      </div>
                      <div className='accordion-icon is-chevron'>
                        <Image
                          src='/assets/img_placeholder/th-4/icon-white-cheveron-down.svg'
                          alt='chevron'
                          width={30}
                          height={30}
                        />
                        <Image
                          src='/assets/img_placeholder/th-4/icon-green-cheveron-up.svg'
                          alt='chevron'
                          width={30}
                          height={30}
                          className='absolute inset-0'
                        />
                      </div>
                    </div>
                    <div className='accordion-content disappear translate-y-3 text-lg leading-[1.42] lg:text-[21px]'>
                      <p>
                        You can easily create a custom AI account. You need to
                        input some required information.
                      </p>
                    </div>
                  </li>
                  {/* Accordion items */}
                  {/* Accordion items */}
                  <li
                    className={`jos accordion-item rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                      activeIndex == 1 ? 'active' : ''
                    }`}
                    data-jos_delay='0.1'
                  >
                    <div
                      onClick={() => handleAccordion(1)}
                      className='accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[1px] lg:text-3xl'
                    >
                      <div className='mb-3 flex items-center gap-x-6'>
                        <Image
                          src='/assets/img_placeholder/th-4/icon-green-process-accordion-2.svg'
                          alt='icon-green-process-accordion'
                          width={36}
                          height={50}
                          className='h-[50px] w-auto'
                        />
                        <h5 className='font-spaceGrotesk text-white'>
                          Define clear objectives
                        </h5>
                      </div>
                      <div className='accordion-icon is-chevron'>
                        <Image
                          src='/assets/img_placeholder/th-4/icon-white-cheveron-down.svg'
                          alt='chevron'
                          width={30}
                          height={30}
                        />
                        <Image
                          src='/assets/img_placeholder/th-4/icon-green-cheveron-up.svg'
                          alt='chevron'
                          width={30}
                          height={30}
                          className='absolute inset-0'
                        />
                      </div>
                    </div>
                    <div className='accordion-content disappear translate-y-3 text-lg leading-[1.42] lg:text-[21px]'>
                      <p>
                        You can easily create a custom AI account. You need to
                        input some required information.
                      </p>
                    </div>
                  </li>
                  {/* Accordion items */}
                  {/* Accordion items */}
                  <li
                    className={`jos accordion-item rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                      activeIndex == 2 ? 'active' : ''
                    }`}
                    data-jos_delay='0.1'
                  >
                    <div
                      onClick={() => handleAccordion(2)}
                      className='accordion-header flex items-center justify-between text-xl leading-[1.2] -tracking-[1px] lg:text-3xl'
                    >
                      <div className='mb-3 flex items-center gap-x-6'>
                        <Image
                          src='/assets/img_placeholder/th-4/icon-green-process-accordion-3.svg'
                          alt='icon-green-process-accordion'
                          width={36}
                          height={50}
                          className='h-[50px] w-auto'
                        />
                        <h5 className='font-spaceGrotesk text-white'>
                          Continuous improvement
                        </h5>
                      </div>
                      <div className='accordion-icon is-chevron'>
                        <Image
                          src='/assets/img_placeholder/th-4/icon-white-cheveron-down.svg'
                          alt='chevron'
                          width={30}
                          height={30}
                        />
                        <Image
                          src='/assets/img_placeholder/th-4/icon-green-cheveron-up.svg'
                          alt='chevron'
                          width={30}
                          height={30}
                          className='absolute inset-0'
                        />
                      </div>
                    </div>
                    <div className='accordion-content disappear translate-y-3 text-lg leading-[1.42] lg:text-[21px]'>
                      <p>
                        You can easily create a custom AI account. You need to
                        input some required information.
                      </p>
                    </div>
                  </li>
                  {/* Accordion items */}
                </ul>
                {/* Process Accordion */}
                <div className='jos' data-jos_animation='fade-right'>
                  {/* Section Content Block */}
                  <div className='mb-6'>
                    <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                      Optimize the highest security standards
                    </h2>
                  </div>
                  {/* Section Content Block */}
                  <div>
                    <p className='mb-8 text-lg leading-[1.42] last:mb-0 lg:text-[21px]'>
                      With AI cybersecurity solutions you can also save time and
                      money integrating disparate vendors, reduce training time,
                      and accelerate your time to discovery and response with
                      everything you need.
                    </p>
                  </div>
                  {/* Counter Scroll */}
                  <ul className='mt-[50px] grid grid-cols-1 gap-10 gap-y-5 text-center sm:grid-cols-3'>
                    {/* Counter Items */}
                    <li>
                      <h3
                        className='font-spaceGrotesk text-5xl leading-[1.05] tracking-[-1px] text-colorGreen md:text-5xl lg:text-6xl xl:text-[70px]'
                        data-module='countup'
                      >
                        <span className='start-number' data-countup-number={95}>
                          92
                        </span>
                        %
                      </h3>
                      <span className='mt-4 block text-[21px] font-normal'>
                        Reduce Risk
                      </span>
                    </li>
                    {/* Counter Items */}
                    {/* Counter Items */}
                    <li>
                      <h3
                        className='font-spaceGrotesk text-5xl leading-[1.05] tracking-[-1px] text-colorGreen md:text-5xl lg:text-6xl xl:text-[70px]'
                        data-module='countup'
                      >
                        <span className='start-number' data-countup-number={50}>
                          50
                        </span>
                        %
                      </h3>
                      <span className='mt-4 block text-[21px] font-normal'>
                        Reduce Costs
                      </span>
                    </li>
                    {/* Counter Items */}
                    {/* Counter Items */}
                    <li>
                      <h3
                        className='font-spaceGrotesk text-5xl leading-[1.05] tracking-[-1px] text-colorGreen md:text-5xl lg:text-6xl xl:text-[70px]'
                        data-module='countup'
                      >
                        <span className='start-number' data-countup-number={76}>
                          76
                        </span>
                        %
                      </h3>
                      <span className='mt-4 block text-[21px] font-normal'>
                        Maximize Value
                      </span>
                    </li>
                    {/* Counter Items */}
                  </ul>
                  {/* Counter Scroll */}
                </div>
              </div>
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Content Section-4 End :::... */}
        {/* Separator */}
        <div className='global-container overflow-hidden'>
          <div className='h-[1px] w-full bg-[#363636]' />
        </div>
        {/* Separator */}
        {/*...::: FAQ Section Start :::... */}
        <section className='faq-section'>
          {/* Section Spacer */}
          <div className='py-20 xl:pb-[150px] xl:pt-[130px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mx-auto mb-10 text-center md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[856px]'>
                <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                  Our experts are able to answer all your questions
                </h2>
              </div>
              {/* Section Content Block */}
              {/* Accordion*/}
              <ul className='accordion flex flex-col gap-y-6'>
                {/* Accordion items */}
                <li
                  className={`jos accordion-item is-2 rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                    activeIndexTwo === 0 ? 'active' : ''
                  }`}
                  data-jos_delay='0.1'
                >
                  <div
                    onClick={() => handleAccordionTwo(0)}
                    className='accordion-header mb-[10px] flex items-center justify-between text-xl leading-[1.33] -tracking-[1px] lg:text-3xl'
                  >
                    <h5 className='font-spaceGrotesk text-white'>
                      What is AI cybersecurity, and how does it differ from
                      traditional cybersecurity?
                    </h5>
                    <div className='accordion-icon is-outline-green'>
                      <span className='accordion-icon-plus' />
                    </div>
                  </div>
                  <div className='accordion-content'>
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
                  className={`jos accordion-item is-2 rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                    activeIndexTwo === 1 ? 'active' : ''
                  }`}
                  data-jos_delay='0.1'
                >
                  <div
                    onClick={() => handleAccordionTwo(1)}
                    className='accordion-header mb-[10px] flex items-center justify-between text-xl leading-[1.33] -tracking-[1px] lg:text-3xl'
                  >
                    <h5 className='font-spaceGrotesk text-white'>
                      What types of threats can AI cybersecurity protect
                      against?
                    </h5>
                    <div className='accordion-icon is-outline-green'>
                      <span className='accordion-icon-plus' />
                    </div>
                  </div>
                  <div className='accordion-content'>
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
                  className={`jos accordion-item is-2 rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                    activeIndexTwo === 2 ? 'active' : ''
                  }`}
                  data-jos_delay='0.1'
                >
                  <div
                    onClick={() => handleAccordionTwo(2)}
                    className='accordion-header mb-[10px] flex items-center justify-between text-xl leading-[1.33] -tracking-[1px] lg:text-3xl'
                  >
                    <h5 className='font-spaceGrotesk text-white'>
                      How does AI help in threat detection and prevention?
                    </h5>
                    <div className='accordion-icon is-outline-green'>
                      <span className='accordion-icon-plus' />
                    </div>
                  </div>
                  <div className='accordion-content'>
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
                  className={`jos accordion-item is-2 rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                    activeIndexTwo === 3 ? 'active' : ''
                  }`}
                  data-jos_delay='0.1'
                >
                  <div
                    onClick={() => handleAccordionTwo(3)}
                    className='accordion-header mb-[10px] flex items-center justify-between text-xl leading-[1.33] -tracking-[1px] lg:text-3xl'
                  >
                    <h5 className='font-spaceGrotesk text-white'>
                      Is AI cybersecurity effective against zero-day attacks?
                    </h5>
                    <div className='accordion-icon is-outline-green'>
                      <span className='accordion-icon-plus' />
                    </div>
                  </div>
                  <div className='accordion-content'>
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
                  className={`jos accordion-item is-2 rounded-[10px] bg-[#121212] px-7 py-[30px] ${
                    activeIndexTwo === 4 ? 'active' : ''
                  }`}
                  data-jos_delay='0.1'
                >
                  <div
                    onClick={() => handleAccordionTwo(4)}
                    className='accordion-header mb-[10px] flex items-center justify-between text-xl leading-[1.33] -tracking-[1px] lg:text-3xl'
                  >
                    <h5 className='font-spaceGrotesk text-white'>
                      What is the role of human cybersecurity professionals in
                      AI cybersecurity?
                    </h5>
                    <div className='accordion-icon is-outline-green'>
                      <span className='accordion-icon-plus' />
                    </div>
                  </div>
                  <div className='accordion-content'>
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
        {/*...::: Testimonial Section Start :::... */}
        <section id='testimonial-section'>
          {/* Section Spacer */}
          <div className='pb-20 xl:pb-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              <div className='mb-10 flex flex-wrap items-center justify-between gap-8 md:mb-16 lg:mb-20'>
                {/* Section Content Block */}
                <div className='jos max-w-[480px] lg:max-w-2xl xl:max-w-[840px]'>
                  <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-white sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                    What people are saying about AI cybersecurity
                  </h2>
                </div>
                {/* Section Content Block */}
                <Link
                  rel='noopener noreferrer'
                  href='https://www.example.com'
                  className='button inline-block h-full rounded border-none bg-colorGreen py-3 text-base text-black after:border-none after:bg-white'
                >
                  Read All Trustpilot Reviews
                </Link>
              </div>
            </div>
            {/* Section Container */}
            {/* Testimonial List */}
            <div className='horizontal-slide-from-right-to-left grid w-[200%] grid-flow-col gap-6'>
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  “This AI SaaS tool has revolutionized the way we process and
                  analyze data. This is a game-changer for our business.”
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-1.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Max Weber
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      HR Manager
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  It answers immediately, and we ve seen a significant reduction
                  in response time. Our customers love it and so do we!
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-2.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Douglas Smith
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      Businessman
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  It is accurate, fast and supports multiple languages support.
                  It is a must for any international business success.
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-3.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Abraham Maslo
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      Founder @ Marketing Company
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  Security is a top concern for us, and AI SaaS takes it
                  seriously. It s a reassuring layer of protection for our
                  organization.
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-4.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Jack Fayol
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      HR Manager
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
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
                      width={60}
                      height={60}
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
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
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
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Henry Ochi
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      Bank Manager
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  “This AI SaaS tool has revolutionized the way we process and
                  analyze data. This is a game-changer for our business.”
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-1.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Max Weber
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      HR Manager
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  It answers immediately, and we ve seen a significant reduction
                  in response time. Our customers love it and so do we!
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-2.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Douglas Smith
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      Businessman
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
              {/* Testimonial Item */}
              <div className='flex w-[415px] flex-col gap-y-8 rounded-[10px] border-[1px] border-colorCodGray p-[30px] text-white'>
                <div className='block'>
                  <Image
                    src='/assets/img_placeholder/th-4/icon-green-rating.svg'
                    alt='rating'
                    width={146}
                    height={25}
                  />
                </div>
                <p>
                  It is accurate, fast and supports multiple languages support.
                  It is a must for any international business success.
                </p>
                <div className='flex items-center gap-x-4'>
                  <div className='h-[60px] w-[60px] overflow-hidden rounded-full'>
                    <Image
                      src='/assets/img_placeholder/th-1/testimonial-img-3.jpg'
                      alt='testimonial-img'
                      width={60}
                      height={60}
                      className='h-full w-full object-cover object-center'
                    />
                  </div>
                  <div className='flex flex-col gap-y-1'>
                    <span className='block text-lg font-semibold leading-[1.6]'>
                      Abraham Maslo
                    </span>
                    <span className='block text-sm font-light leading-[1.4]'>
                      Founder @ Marketing Company
                    </span>
                  </div>
                </div>
              </div>
              {/* Testimonial Item */}
            </div>
            {/* Testimonial List */}
          </div>
        </section>
        {/*...::: Testimonial Section End :::... */}
        {/*...::: CTA Section Start :::... */}
        <section id='cta-section'>
          <div className='global-container'>
            <div className='rounded-[10px] bg-colorGreen px-5 py-[60px] md:py-20 xl:py-[100px]'>
              {/* Section Content Block */}
              <div className='jos mx-auto max-w-[500px] text-center lg:max-w-2xl xl:max-w-[840px]'>
                <h2 className='font-spaceGrotesk text-4xl font-medium leading-[1.06] -tracking-[2px] text-black sm:text-[44px] lg:text-[56px] xl:text-[70px]'>
                  Protect your organization with the power of AI
                </h2>
              </div>
              {/* Section Content Block */}
              <div
                className='jos mt-8 flex flex-wrap justify-center gap-6 md:mt-[50px]'
                data-jos_animation='fade'
              >
                <Link
                  rel='noopener noreferrer'
                  href='https://www.example.com'
                  className='button inline-block h-full rounded border-2 border-transparent bg-black py-3 text-base text-colorGreen after:border-colorGreen after:bg-colorGreen hover:text-black'
                >
                  Get Started Now
                </Link>
                <Link
                  href='/pricing'
                  className='button inline-block h-full rounded border-2 border-black bg-colorGreen py-3 text-base text-black after:bg-black hover:text-colorGreen'
                >
                  View Our Plans
                </Link>
              </div>
            </div>
          </div>
        </section>
        {/*...::: CTA Section End :::... */}
      </main>
    </>
  );
};

export default Home_4;
