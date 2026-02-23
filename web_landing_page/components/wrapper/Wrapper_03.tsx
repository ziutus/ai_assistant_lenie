import Header_03 from '../header/Header_03';
import Footer_03 from '../footer/Footer_03';

const Wrapper_03 = ({ children }: { children: React.ReactNode }) => {
  return (
    <div className='page-wrapper relative z-[1] bg-[#F6F6EB]'>
      {/*...::: Header Start :::... */}
      <Header_03 />
      {/*...::: Header End :::... */}

      {/*...::: Main Start :::... */}
      {children}
      {/*...::: Main End :::... */}

      {/*...::: Footer Start :::... */}
      <Footer_03 />
      {/*...::: Footer End :::... */}
    </div>
  );
};

export default Wrapper_03;
