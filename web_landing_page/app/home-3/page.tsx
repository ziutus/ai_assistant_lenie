'use client';
import Image from 'next/image';
import Link from 'next/link';

function Home_3() {
  return (
    <>
      <main className='main-wrapper relative overflow-hidden'>
        {/*...::: Hero Section Start :::... */}
        <section id='hero-section'>
          {/* Section Spacer */}
          <div className='pt-28 lg:pt-40 xl:pt-[195px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Hero Content */}
              <div className='grid items-center gap-10 md:grid-cols-2 xl:grid-cols-[minmax(0,_1.3fr)_1fr]'>
                {/* Section Content Block */}
                <div>
                  <h2 className='font-raleway text-5xl md:text-6xl lg:text-7xl xl:text-[100px] xxl:text-[120px]'>
                    AI the future of business
                  </h2>
                </div>
                {/* Section Content Block */}
                <div className='jos flex flex-col gap-10 md:gap-[50px]'>
                  <p className='text-lg font-semibold leading-[1.33] md:text-xl lg:text-2xl'>
                    Businesses harnessing AI s power are better positioned to
                    thrive in the modern age. It can drive decision-making
                    skills.
                  </p>
                  <Link
                    href='/about'
                    className='button inline-block rounded-[50px] border-2 border-black bg-[#F6F6EB] text-black after:border-colorOrangyRed after:bg-colorOrangyRed hover:text-white'
                  >
                    Explore About Us
                  </Link>
                </div>
              </div>
              {/* Hero Content */}
            </div>
            {/* Section Container */}
            {/* Hero Image */}
            <div
              className='jos mx-auto mt-12 max-w-[1500px] px-5 md:mt-20'
              data-jos_animation='zoom'
            >
              <Image
                src='/assets/img_placeholder/th-3/hero-img.jpg'
                alt='hero-img'
                width={1500}
                height={700}
                className='h-auto w-full'
              />
            </div>
            {/* Hero Image */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Hero Section End :::... */}
        {/*...::: Promo Section Start :::... */}
        <section id='promo-section'>
          {/* Section Spacer */}
          <div className='pb-20 pt-20 xl:pb-[130px] xl:pt-[150px]'>
            {/* Section Container */}
            <div className='global-container'>
              {/* Section Content Block */}
              <div className='jos mx-auto mb-10 text-center md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[1000px]'>
                <h2 className='font-raleway text-4xl font-medium leading-[1.06] sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                  Way to be a game changer
                </h2>
              </div>
              {/* Section Content Block */}
              {/* Promo List */}
              <ul className='grid gap-x-6 gap-y-12 md:grid-cols-2 lg:grid-cols-3'>
                {/* Promo Item */}
                <li
                  className='jos text-center md:text-left'
                  data-jos_delay='0.1'
                >
                  <div className='mx-auto mb-[30px] inline-flex h-10 w-auto justify-center md:justify-normal xxl:h-[60px]'>
                    <Image
                      src='/assets/img_placeholder/th-3/icon-black-promo-1.svg'
                      alt='icon-black-promo-1'
                      width={60}
                      height={60}
                      className='h-full w-auto'
                    />
                  </div>
                  <div className='mb-5 font-raleway text-2xl font-bold leading-[1.33] text-black xl:text-3xl'>
                    Enhanced Decision-Making
                  </div>
                  <p className='text-lg leading-[1.42] xl:text-[21px]'>
                    AI can uncover valuable insights, for an identify trends,
                    &amp; predict outcomes. AI empowers data-driven decisions.
                  </p>
                </li>
                {/* Promo Item */}
                {/* Promo Item */}
                <li
                  className='jos text-center md:text-left'
                  data-jos_delay='0.2'
                >
                  <div className='mx-auto mb-[30px] inline-flex h-10 w-auto justify-center md:justify-normal xxl:h-[60px]'>
                    <Image
                      src='/assets/img_placeholder/th-3/icon-black-promo-2.svg'
                      alt='icon-black-promo-1'
                      width={70}
                      height={60}
                      className='h-full w-auto'
                    />
                  </div>
                  <div className='mb-5 font-raleway text-2xl font-bold leading-[1.33] text-black xl:text-3xl'>
                    Efficiency and Automation
                  </div>
                  <p className='text-lg leading-[1.42] xl:text-[21px]'>
                    AI driven automation can be applied to the various processes
                    leading to cost savings &amp; improved productivity.
                  </p>
                </li>
                {/* Promo Item */}
                {/* Promo Item */}
                <li
                  className='jos text-center md:text-left'
                  data-jos_delay='0.3'
                >
                  <div className='mx-auto mb-[30px] inline-flex h-10 w-auto justify-center md:justify-normal xxl:h-[60px]'>
                    <Image
                      src='/assets/img_placeholder/th-3/icon-black-promo-3.svg'
                      alt='icon-black-promo-1'
                      width={67}
                      height={60}
                      className='h-full w-auto'
                    />
                  </div>
                  <div className='mb-5 font-raleway text-2xl font-bold leading-[1.33] text-black xl:text-3xl'>
                    Customer Experiences
                  </div>
                  <p className='text-lg leading-[1.42] xl:text-[21px]'>
                    It enables businesses to provide highly personalized and
                    responsive innovative best customer experiences.
                  </p>
                </li>
                {/* Promo Item */}
              </ul>
              {/* Promo List */}
            </div>
            {/* Section Container */}
          </div>
          {/* Section Spacer */}
        </section>
        {/*...::: Promo Section End :::... */}
        {/*...::: Content Section-1 Start :::... */}
        <section id='section-content-1'>
          <div className='bg-[#EDEDE0]'>
            {/* Section Spacer */}
            <div className='py-20 xl:py-[130px]'>
              {/* Section Container */}
              <div className='global-container'>
                <div className='grid items-center gap-10 md:grid-cols-[minmax(0,_1fr)_1.3fr] lg:gap-[60px] xl:gap-x-[94px]'>
                  <div className='jos' data-jos_animation='fade-left'>
                    <div className='overflow-hidden rounded-[10px]'>
                      <Image
                        src='/assets/img_placeholder/th-3/content-img-1.jpg'
                        alt='content-img-1'
                        width={526}
                        height={550}
                        className='h-auto w-full'
                      />
                    </div>
                  </div>
                  <div className='jos' data-jos_animation='fade-right'>
                    {/* Section Content Block */}
                    <div className='mb-6'>
                      <h2 className='font-raleway text-4xl font-medium leading-[1.06] sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                        Revolutionary AI superchargers all business tasks
                      </h2>
                    </div>
                    {/* Section Content Block */}
                    <div className=''>
                      <p className='mb-8 text-lg leading-[1.33] last:mb-0 lg:text-xl xl:text-2xl'>
                        AI technologies and applications that significantly
                        enhance and accelerate various business operations and
                        tasks.
                      </p>
                      <p className='mb-8 text-lg leading-[1.33] last:mb-0 lg:text-xl xl:text-2xl'>
                        <span className='font-semibold text-[#381FD1]'>
                          AI-Powered Analytics:
                        </span>
                        Advanced AI analytics platforms can process and actions
                        to improve decision-making.
                      </p>
                      <p className='mb-8 text-lg leading-[1.33] last:mb-0 lg:text-xl xl:text-2xl'>
                        <span className='font-semibold text-[#381FD1]'>
                          Competitive Advantage:
                        </span>
                        Companies that embrace AI can gain a competitive edge
                        &amp; help businesses innovate and stay ahead of
                        competitors.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              {/* Section Container */}
            </div>
            {/* Section Spacer */}
          </div>
        </section>
        {/*...::: Content Section-1 End :::... */}
        {/*...::: Working Process Start :::... */}
        <section id='section-working-process'>
          <div className='bg-[#EDEDE0] px-5 sm:px-[50px]'>
            <div className='relative z-[1] mx-auto max-w-full rounded-[20px] bg-black'>
              {/* Section Spacer */}
              <div className='py-16 sm:px-10 md:px-20 lg:py-20 xl:px-[100px] xl:py-[130px]'>
                {/* Section Container */}
                <div className='global-container'>
                  {/* Section Content Block */}
                  <div className='jos mx-auto mb-10 text-center md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[1000px]'>
                    <h2 className='font-raleway text-4xl font-medium leading-[1.06] text-white sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                      Solutions for smart work
                    </h2>
                  </div>
                  {/* Section Content Block */}
                  {/* Work Process List */}
                  <div className='grid grid-flow-dense gap-6 lg:grid-cols-2 xl:grid-cols-3'>
                    {/* Work Process Item */}
                    <div className='order-1 col-span-1 flex flex-col gap-y-8 rounded-[10px] bg-[#121212] p-[30px] text-white transition-all duration-300 hover:bg-[#381FD1]'>
                      <div className='h-10 w-auto xxl:h-[60px]'>
                        <Image
                          src='/assets/img_placeholder/th-3/icon-black-work-process-1.svg'
                          alt='working-process-icon'
                          width={62}
                          height={60}
                          className='h-full'
                        />
                      </div>
                      <div className='font-raleway text-2xl font-bold leading-[1.33] lg:text-3xl'>
                        Data Analysis
                      </div>
                      <p className='text-xl leading-[1.33] lg:text-2xl'>
                        AI can analyze large volumes of data quickly and
                        accurately
                      </p>
                      <Link
                        rel='noopener noreferrer'
                        href='https://www.example.com'
                        className='h-[30px] w-[30px]'
                      >
                        <Image
                          src='/assets/img_placeholder/th-3/icon-white-arrow-right.svg'
                          alt='icon-white-arrow-right'
                          width={30}
                          height={30}
                        />
                      </Link>
                    </div>
                    {/* Work Process Item */}
                    {/* Work Process Item */}
                    <div className='order-2 col-span-1 flex flex-col gap-y-8 rounded-[10px] bg-[#121212] p-[30px] text-white transition-all duration-300 hover:bg-[#381FD1]'>
                      <div className='h-10 w-auto xxl:h-[60px]'>
                        <Image
                          src='/assets/img_placeholder/th-3/icon-black-work-process-2.svg'
                          alt='working-process-icon'
                          width={60}
                          height={60}
                          className='h-full'
                        />
                      </div>
                      <div className='font-raleway text-2xl font-bold leading-[1.33] lg:text-3xl'>
                        Automation
                      </div>
                      <p className='text-xl leading-[1.33] lg:text-2xl'>
                        AI can automate repetitive and time consuming, reducing
                        error
                      </p>
                      <Link
                        rel='noopener noreferrer'
                        href='https://www.example.com'
                        className='h-[30px] w-[30px]'
                      >
                        <Image
                          src='/assets/img_placeholder/th-3/icon-white-arrow-right.svg'
                          alt='icon-white-arrow-right'
                          width={30}
                          height={30}
                        />
                      </Link>
                    </div>
                    {/* Work Process Item */}
                    {/* Work Process Item */}
                    <div className='order-3 col-span-1 flex flex-col gap-y-8 rounded-[10px] bg-[#121212] p-[30px] text-white transition-all duration-300 hover:bg-[#381FD1]'>
                      <div className='h-10 w-auto xxl:h-[60px]'>
                        <Image
                          src='/assets/img_placeholder/th-3/icon-black-work-process-3.svg'
                          alt='working-process-icon'
                          width={60}
                          height={60}
                          className='h-full'
                        />
                      </div>
                      <div className='font-raleway text-2xl font-bold leading-[1.33] lg:text-3xl'>
                        Personalization
                      </div>
                      <p className='text-xl leading-[1.33] lg:text-2xl'>
                        Businesses to deliver highly personalized high
                        experiences
                      </p>
                      <Link
                        rel='noopener noreferrer'
                        href='https://www.example.com'
                        className='h-[30px] w-[30px]'
                      >
                        <Image
                          src='/assets/img_placeholder/th-3/icon-white-arrow-right.svg'
                          alt='icon-white-arrow-right'
                          width={30}
                          height={30}
                        />
                      </Link>
                    </div>
                    {/* Work Process Item */}
                    <div className='order-1 col-span-full grid gap-6 lg:grid-cols-2 xl:order-2 xl:grid-cols-2'>
                      {/* Work Process Item */}
                      <div className='col-span-1 flex flex-col gap-y-8 rounded-[10px] bg-[#121212] p-[30px] text-white transition-all duration-300 hover:bg-[#381FD1]'>
                        <div className='h-10 w-auto xxl:h-[60px]'>
                          <Image
                            src='/assets/img_placeholder/th-3/icon-black-work-process-4.svg'
                            alt='working-process-icon'
                            width={65}
                            height={60}
                            className='h-full'
                          />
                        </div>
                        <div className='font-raleway text-2xl font-bold leading-[1.33] lg:text-3xl'>
                          Cost Savings
                        </div>
                        <p className='text-xl leading-[1.33] lg:text-2xl'>
                          By automating tasks and optimizing processes, AI can
                          lead to significant cost savings over time
                        </p>
                        <Link
                          rel='noopener noreferrer'
                          href='https://www.example.com'
                          className='h-[30px] w-[30px]'
                        >
                          <Image
                            src='/assets/img_placeholder/th-3/icon-white-arrow-right.svg'
                            alt='icon-white-arrow-right'
                            width={30}
                            height={30}
                          />
                        </Link>
                      </div>
                      {/* Work Process Item */}
                      {/* Work Process Item */}
                      <div className='col-span-1 flex flex-col gap-y-8 rounded-[10px] bg-[#121212] p-[30px] text-white transition-all duration-300 hover:bg-[#381FD1]'>
                        <div className='h-10 w-auto xxl:h-[60px]'>
                          <Image
                            src='/assets/img_placeholder/th-3/icon-black-work-process-5.svg'
                            alt='working-process-icon'
                            width={40}
                            height={60}
                            className='h-full'
                          />
                        </div>
                        <div className='font-raleway text-2xl font-bold leading-[1.33] lg:text-3xl'>
                          Risk Management
                        </div>
                        <p className='text-xl leading-[1.33] lg:text-2xl'>
                          AI can assess &amp; mitigate risks more accurately by
                          analyzing vast amounts of data &amp; reduce risks
                        </p>
                        <Link
                          rel='noopener noreferrer'
                          href='https://www.example.com'
                          className='h-[30px] w-[30px]'
                        >
                          <Image
                            src='/assets/img_placeholder/th-3/icon-white-arrow-right.svg'
                            alt='icon-white-arrow-right'
                            width={30}
                            height={30}
                          />
                        </Link>
                      </div>
                      {/* Work Process Item */}
                    </div>
                  </div>
                  {/* Work Process List */}
                </div>
                {/* Section Container */}
              </div>
              {/* Section Spacer */}
              {/* Vertical Line */}
              <div className='absolute left-0 top-0 -z-[1] flex h-full w-full justify-evenly'>
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
                <div className='h-full w-[1px] bg-[#121212]' />
              </div>
              {/* Vertical Line */}
            </div>
          </div>
        </section>
        {/*...::: Working Process End :::... */}
        {/*...::: Content Section-2 Start :::... */}
        <section id='section-content-2'>
          <div className='bg-[#EDEDE0]'>
            {/* Section Spacer */}
            <div className='py-20 xl:py-[130px]'>
              {/* Section Container */}
              <div className='global-container'>
                <div className='grid items-center gap-10 md:grid-cols-[1.3fr_minmax(0,_1fr)] lg:gap-[60px] xl:gap-x-[94px]'>
                  <div className='jos order-2' data-jos_animation='fade-left'>
                    <div className='overflow-hidden rounded-[10px]'>
                      <Image
                        src='/assets/img_placeholder/th-3/content-img-2.jpg'
                        alt='content-img-2'
                        width={526}
                        height={550}
                        className='h-auto w-full'
                      />
                    </div>
                  </div>
                  <div className='jos order-1' data-jos_animation='fade-right'>
                    {/* Section Content Block */}
                    <div className='mb-6'>
                      <h2 className='font-raleway text-4xl font-medium leading-[1.06] sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                        AI is reshaping all future-proofing work activities
                      </h2>
                    </div>
                    {/* Section Content Block */}
                    <div className=''>
                      <p className='mb-8 text-lg leading-[1.33] last:mb-0 lg:text-xl xl:text-2xl'>
                        AI is indeed reshaping &amp; future-proofing work
                        activities. AI is playing a crucial role in automating
                        decision-making.
                      </p>
                      <p className='mb-8 text-lg leading-[1.33] last:mb-0 lg:text-xl xl:text-2xl'>
                        <span className='font-semibold text-[#381FD1]'>
                          Adaptive Workforces:
                        </span>
                        Adapt to changing market conditions by providing
                        insights into workforce needs and skill gaps.
                      </p>
                      <p className='mb-8 text-lg leading-[1.33] last:mb-0 lg:text-xl xl:text-2xl'>
                        <span className='font-semibold text-[#381FD1]'>
                          Learning and Development:
                        </span>
                        AI-powered platforms offer personalized learning
                        experiences and skill development.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              {/* Section Container */}
            </div>
            {/* Section Spacer */}
          </div>
        </section>
        {/*...::: Content Section-2 End :::... */}
        {/* Separator */}
        <div className='global-container overflow-hidden'>
          <div className='h-[1px] w-full bg-[#F6F6EB]' />
        </div>
        {/* Separator */}
        {/*...::: Team Section Start :::... */}
        <section id='team-section'>
          <div className='bg-[#EDEDE0]'>
            {/* Section Spacer */}
            <div className='py-20 xl:py-[130px]'>
              {/* Section Container */}
              <div className='global-container'>
                {/* Section Content Block */}
                <div className='jos mx-auto mb-10 text-center md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[1000px]'>
                  <h2 className='font-raleway text-4xl font-medium leading-[1.06] sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                    Our professionals help you
                  </h2>
                </div>
                {/* Section Content Block */}
                {/* Team Member List */}
                <div className='grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3'>
                  {/* Team Member Item */}
                  <div
                    className='jos rounded-[20px] bg-[#F6F6EB] p-[20px]'
                    data-jos_animation='flip'
                    data-jos_delay='0.1'
                  >
                    <div className='xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]'>
                      <Image
                        src='/assets/img_placeholder/th-1/team-member-img-1.jpg'
                        alt='team-member-img-1'
                        width={376}
                        height={400}
                        className='h-full w-full object-cover'
                      />
                    </div>
                    <div className='mt-5'>
                      <Link
                        href='/team-details'
                        className='font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]'
                      >
                        Mr. Abraham Maslo
                      </Link>
                      <div className='mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center'>
                        <span className='text-[21px]'>Chief AI Officer</span>
                        <ul className='mt-auto flex gap-x-[15px]'>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.facebook.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/facebook-icon-white.svg'
                                alt='facebook'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/facebook-icon-black.svg'
                                alt='facebook'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.twitter.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/twitter-icon-white.svg'
                                alt='twitter'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/twitter-icon-black.svg'
                                alt='twitter'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.linkedin.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/linkedin-icon-white.svg'
                                alt='linkedin'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/linkedin-icon-black.svg'
                                alt='linkedin'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.instagram.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/instagram-icon-white.svg'
                                alt='instagram'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/instagram-icon-black.svg'
                                alt='instagram'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                        </ul>
                      </div>
                    </div>
                  </div>
                  {/* Team Member Item */}
                  {/* Team Member Item */}
                  <div
                    className='jos rounded-[20px] bg-[#F6F6EB] p-[20px]'
                    data-jos_animation='flip'
                    data-jos_delay='0.2'
                  >
                    <div className='xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]'>
                      <Image
                        src='/assets/img_placeholder/th-1/team-member-img-2.jpg'
                        alt='team-member-img-2'
                        width={376}
                        height={400}
                        className='h-full w-full object-cover'
                      />
                    </div>
                    <div className='mt-5'>
                      <Link
                        href='/team-details'
                        className='font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]'
                      >
                        Willium Robert
                      </Link>
                      <div className='mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center'>
                        <span className='text-[21px]'>Data Engineer</span>
                        <ul className='mt-auto flex gap-x-[15px]'>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.facebook.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/facebook-icon-white.svg'
                                alt='facebook'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/facebook-icon-black.svg'
                                alt='facebook'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.twitter.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/twitter-icon-white.svg'
                                alt='twitter'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/twitter-icon-black.svg'
                                alt='twitter'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.linkedin.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/linkedin-icon-white.svg'
                                alt='linkedin'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/linkedin-icon-black.svg'
                                alt='linkedin'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.instagram.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/instagram-icon-white.svg'
                                alt='instagram'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/instagram-icon-black.svg'
                                alt='instagram'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                        </ul>
                      </div>
                    </div>
                  </div>
                  {/* Team Member Item */}
                  {/* Team Member Item */}
                  <div
                    className='jos rounded-[20px] bg-[#F6F6EB] p-[20px]'
                    data-jos_animation='flip'
                    data-jos_delay='0.3'
                  >
                    <div className='xl:h[300px] w-full overflow-hidden rounded-[20px] xxl:h-[400px]'>
                      <Image
                        src='/assets/img_placeholder/th-1/team-member-img-3.jpg'
                        alt='team-member-img-3'
                        width={376}
                        height={400}
                        className='h-full w-full object-cover'
                      />
                    </div>
                    <div className='mt-5'>
                      <Link
                        href='/team-details'
                        className='font-dmSans text-[26px] leading-[1.33] hover:text-colorOrangyRed xxl:text-[30px]'
                      >
                        Henry Fayol
                      </Link>
                      <div className='mt-3 flex flex-col justify-between gap-3 xxl:flex-row xxl:flex-wrap xxl:items-center'>
                        <span className='text-[21px]'>Research Scientist</span>
                        <ul className='mt-auto flex gap-x-[15px]'>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.facebook.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/facebook-icon-white.svg'
                                alt='facebook'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/facebook-icon-black.svg'
                                alt='facebook'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.twitter.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/twitter-icon-white.svg'
                                alt='twitter'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/twitter-icon-black.svg'
                                alt='twitter'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.linkedin.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/linkedin-icon-white.svg'
                                alt='linkedin'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/linkedin-icon-black.svg'
                                alt='linkedin'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                          <li>
                            <Link
                              rel='noopener noreferrer'
                              href='http://www.instagram.com'
                              className='group relative flex h-[30px] w-[30px] items-center justify-center rounded-[50%] bg-black hover:bg-colorOrangyRed'
                            >
                              <Image
                                src='/assets/img_placeholder/th-1/instagram-icon-white.svg'
                                alt='instagram'
                                width={14}
                                height={14}
                                className='opacity-100 group-hover:opacity-0'
                              />
                              <Image
                                src='/assets/img_placeholder/th-1/instagram-icon-black.svg'
                                alt='instagram'
                                width={14}
                                height={14}
                                className='absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100'
                              />
                            </Link>
                          </li>
                        </ul>
                      </div>
                    </div>
                  </div>
                  {/* Team Member Item */}
                </div>
                {/* Team Member List */}
              </div>
              {/* Section Container */}
            </div>
            {/* Section Spacer */}
          </div>
        </section>
        {/*...::: Team Section End :::... */}
        {/*...::: Testimonial Start :::... */}
        <section id='testimonial-section'>
          <div className='bg-[#EDEDE0] px-5 sm:px-[50px]'>
            <div className='relative z-[1] mx-auto max-w-full rounded-[20px] bg-[#381FD1]'>
              {/* Section Spacer */}
              <div className='py-16 sm:px-10 md:px-20 lg:py-20 xl:px-[100px] xl:py-[130px]'>
                {/* Section Container */}
                <div className='global-container'>
                  {/* Section Content Block */}
                  <div className='jos mb-10 md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[677px]'>
                    <h2 className='font-raleway text-4xl font-medium leading-[1.06] text-white sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                      Our clients share their experiences
                    </h2>
                  </div>
                  {/* Section Content Block */}
                  {/* Testimonial  List */}
                  <ul className='grid gap-x-10 gap-y-8 md:grid-cols-2'>
                    {/* Testimonial Item */}
                    <li
                      className='jos flex flex-col gap-y-6 text-white md:gap-y-[30px]'
                      data-jos_delay='0.1'
                    >
                      <div className='h-auto w-[146px]'>
                        <Image
                          src='/assets/img_placeholder/th-3/review-star.svg'
                          alt='review-star'
                          width={146}
                          height={24}
                        />
                      </div>
                      <p className='font-raleway text-lg font-bold leading-[1.33] lg:text-xl xl:text-2xl xxl:text-3xl'>
                        I cant believe the difference AI has made for our
                        marketing efforts and Thanks to AI-powered analytics and
                        30% increase in conversion rates. Highly recommended!
                      </p>
                      <div className='text-[21px] font-semibold leading-[1.42]'>
                        -Jack Liamba
                        <span className='mt-[5px] block text-lg font-normal leading-[1.66]'>
                          Marketing Manager
                        </span>
                      </div>
                    </li>
                    {/* Testimonial Item */}
                    {/* Testimonial Item */}
                    <li
                      className='jos flex flex-col gap-y-6 text-white md:gap-y-[30px]'
                      data-jos_delay='0.2'
                    >
                      <div className='h-auto w-[146px]'>
                        <Image
                          src='/assets/img_placeholder/th-3/review-star.svg'
                          alt='review-star'
                          width={146}
                          height={24}
                        />
                      </div>
                      <p className='font-raleway text-lg font-bold leading-[1.33] lg:text-xl xl:text-2xl xxl:text-3xl'>
                        Our supply chain has never run smoother since we
                        implemented AI-driven logistics, and we ve eliminated
                        costly delays. AI has truly future-proofed our
                        operations.
                      </p>
                      <div className='text-[21px] font-semibold leading-[1.42]'>
                        -Sarah Milan
                        <span className='mt-[5px] block text-lg font-normal leading-[1.66]'>
                          Supply Chain Director
                        </span>
                      </div>
                    </li>
                    {/* Testimonial Item */}
                  </ul>
                  {/* Testimonial List */}
                </div>
                {/* Section Container */}
              </div>
              {/* Section Spacer */}
              {/* Vertical Line */}
              <div className='absolute left-0 top-0 -z-[1] flex h-full w-full justify-evenly'>
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
                <div className='h-full w-[1px] bg-[#F6F6EB1A] bg-opacity-10' />
              </div>
              {/* Vertical Line */}
            </div>
          </div>
        </section>
        {/*...::: Testimonial End :::... */}
        {/*...::: Blog Start :::... */}
        <section id='section-blog'>
          <div className='bg-[#EDEDE0]'>
            {/* Section Spacer */}
            <div className='pb-20 pt-20 xl:pb-[130px] xl:pt-[150px]'>
              {/* Section Container */}
              <div className='global-container'>
                {/* Section Content Block */}
                <div className='jos mx-auto mb-10 text-center md:mb-16 md:max-w-xl lg:mb-20 lg:max-w-3xl xl:max-w-[1000px]'>
                  <h2 className='font-raleway text-4xl font-medium leading-[1.06] sm:text-[44px] lg:text-[56px] xl:text-[80px]'>
                    Discover our latest articles
                  </h2>
                </div>
                {/* Section Content Block */}
                {/* Blog List */}
                <div className='grid grid-cols-1 gap-6 md:grid-cols-2'>
                  {/* Blog Item */}
                  <div className='jos group flex flex-col items-center gap-x-6 gap-y-8 rounded-[20px] bg-[#F6F6EB] p-5 xl:flex-row'>
                    <Link
                      href='/blog-details'
                      className='h-[230px] w-full overflow-hidden rounded-[10px] xl:w-[250px]'
                    >
                      <Image
                        src='/assets/img_placeholder/th-1/blog-main-1.jpg'
                        alt='blog-main-1'
                        width={856}
                        height={450}
                        className='h-full w-full scale-100 object-cover transition-all duration-300 ease-linear group-hover:scale-105'
                      />
                    </Link>
                    <div className='flex-1'>
                      <div className='mb-6 text-sm'>
                        <Link href='/blog'>BUSINESS</Link> |
                        <span>June 12, 2024</span>
                      </div>
                      <Link
                        href='/blog-details'
                        className='font-raleway text-2xl font-bold leading-[1.33] text-black transition-all duration-300 group-hover:text-[#381FD1] lg:text-3xl'
                      >
                        10 AI business ideas for startups in 2024
                      </Link>
                      <p className='mt-3 line-clamp-2 text-lg leading-[1.42] lg:text-[21px]'>
                        Boost business efficiency using AI. Explore AI business
                        ideas...
                      </p>
                    </div>
                  </div>
                  {/* Blog Item */}
                  {/* Blog Item */}
                  <div className='jos group flex flex-col items-center gap-x-6 gap-y-8 rounded-[20px] bg-[#F6F6EB] p-5 xl:flex-row'>
                    <Link
                      href='/blog-details'
                      className='h-[230px] w-full overflow-hidden rounded-[10px] xl:w-[250px]'
                    >
                      <Image
                        src='/assets/img_placeholder/th-1/blog-main-2.jpg'
                        alt='blog-main-2'
                        width={856}
                        height={450}
                        className='h-full w-full scale-100 object-cover transition-all duration-300 ease-linear group-hover:scale-105'
                      />
                    </Link>
                    <div className='flex-1'>
                      <div className='mb-6 text-sm'>
                        <Link href='/blog'>OPINION</Link> |
                        <span>June 10, 2024</span>
                      </div>
                      <Link
                        href='/blog-details'
                        className='font-raleway text-2xl font-bold leading-[1.33] text-black transition-all duration-300 group-hover:text-[#381FD1] lg:text-3xl'
                      >
                        Steps to shape your future work with AI
                      </Link>
                      <p className='mt-3 line-clamp-2 text-lg leading-[1.42] lg:text-[21px]'>
                        Artificial Intelligence has the potential to
                        revolutionize...
                      </p>
                    </div>
                  </div>
                  {/* Blog Item */}
                  {/* Blog Item */}
                  <div className='jos group flex flex-col items-center gap-x-6 gap-y-8 rounded-[20px] bg-[#F6F6EB] p-5 xl:flex-row'>
                    <Link
                      href='/blog-details'
                      className='h-[230px] w-full overflow-hidden rounded-[10px] xl:w-[250px]'
                    >
                      <Image
                        src='/assets/img_placeholder/th-1/blog-main-3.jpg'
                        alt='blog-main-3'
                        width={856}
                        height={450}
                        className='h-full w-full scale-100 object-cover transition-all duration-300 ease-linear group-hover:scale-105'
                      />
                    </Link>
                    <div className='flex-1'>
                      <div className='mb-6 text-sm'>
                        <Link href='/blog'>TECHNOLOGY</Link> |
                        <span>June 09, 2024</span>
                      </div>
                      <Link
                        href='/blog-details'
                        className='font-raleway text-2xl font-bold leading-[1.33] text-black transition-all duration-300 group-hover:text-[#381FD1] lg:text-3xl'
                      >
                        AI tools to improve product descriptions
                      </Link>
                      <p className='mt-3 line-clamp-2 text-lg leading-[1.42] lg:text-[21px]'>
                        AI tools are designed to help sellers generate
                        improved...
                      </p>
                    </div>
                  </div>
                  {/* Blog Item */}
                  {/* Blog Item */}
                  <div className='jos group flex flex-col items-center gap-x-6 gap-y-8 rounded-[20px] bg-[#F6F6EB] p-5 xl:flex-row'>
                    <Link
                      href='/blog-details'
                      className='h-[230px] w-full overflow-hidden rounded-[10px] xl:w-[250px]'
                    >
                      <Image
                        src='/assets/img_placeholder/th-1/blog-main-4.jpg'
                        alt='blog-main-4'
                        width={856}
                        height={450}
                        className='h-full w-full scale-100 object-cover transition-all duration-300 ease-linear group-hover:scale-105'
                      />
                    </Link>
                    <div className='flex-1'>
                      <div className='mb-6 text-sm'>
                        <Link href='/blog'>BUSINESS</Link> |
                        <span>June 06, 2024</span>
                      </div>
                      <Link
                        href='/blog-details'
                        className='font-raleway text-2xl font-bold leading-[1.33] text-black transition-all duration-300 group-hover:text-[#381FD1] lg:text-3xl'
                      >
                        3 best AI businesses to make money
                      </Link>
                      <p className='mt-3 line-clamp-2 text-lg leading-[1.42] lg:text-[21px]'>
                        Everyone is buzzing about AI &amp; its potential to
                        revolutionize...
                      </p>
                    </div>
                  </div>
                  {/* Blog Item */}
                </div>
                {/* Blog List */}
              </div>
              {/* Section Container */}
            </div>
            {/* Section Spacer */}
          </div>
        </section>
        {/*...::: Blog End :::... */}
      </main>
      {/* Vertical Line */}
      <div className='absolute left-0 top-0 -z-[1] flex h-full w-full justify-evenly'>
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
        <div className='h-full w-[1px] bg-[#EDEDE0]' />
      </div>
      {/* Vertical Line */}
    </>
  );
}

export default Home_3;
