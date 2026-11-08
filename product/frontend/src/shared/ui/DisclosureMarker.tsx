import RightOutlined from '@ant-design/icons/RightOutlined'

export function DisclosureMarker({expanded}:{expanded:boolean}){
  return <RightOutlined className="jj-disclosure-marker" data-expanded={expanded} aria-hidden="true"/>
}
