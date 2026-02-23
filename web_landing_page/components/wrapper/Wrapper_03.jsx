import Header_03 from '../header/Header_03';
import Footer_03 from '../footer/Footer_03';

// eslint-disable-next-line react/prop-types
const Wrapper_03 = ({ children }) => {
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
